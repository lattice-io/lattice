import abc
import signal
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from lattice.elastic.worker.api import (
    WorkerState,
    WorkerGroup,
    WorkerSpec,
    Worker,
    worker_registry,
)
import lattice.elastic.utils.store as store_util
from lattice.elastic.utils.logging import get_logger
from lattice.elastic.utils.store import (
    set_master_addr_port
)
from lattice.elastic.multiprocessing import (
    ProcessFailure,
    SignalException
)
from lattice.elastic.multiprocessing.errors import ErrorType
from lattice.elastic.rendezvous.store import Store


_TERMINAL_STATE_SYNC_ID = "torchelastic/agent/terminal_state"


DEFAULT_ROLE = "default"
log = get_logger()


@dataclass
class RunResult:
    r"""
    Results returned by the worker executions. Run results follow an "all-or-nothing" policy
    where the run is successful if and only if ALL local workers managed by this agent
    complete successfully.

    If the result is successful (e.g. ``is_failed() = False``) then the ``return_values``
    field contains the outputs (return values) of the workers managed by THIS agent mapped
    by their GLOBAL ranks. That is ``result.return_values[0]`` is the return value of
    global rank 0.

    .. note:: ``return_values`` are only meaningful for when the worker entrypoint
              is a function. Workers specified as a binary entrypoint do not canonically
              have a return value and the ``return_values`` field is meaningless and
              may be empty.

    If ``is_failed()`` returns ``True`` then the ``failures`` field contains the
    failure information, again, mapped by the GLOBAL rank of the worker that failed.

    The keys in ``return_values`` and ``failures`` are mutually exclusive, that is,
    a worker's final state can only be one of: succeeded, failed. Workers intentionally
    terminated by the agent according to the agent's restart policy, are not represented
    in either ``return_values`` nor ``failures``.
    """

    state: WorkerState
    return_values: Dict[int, Any] = field(default_factory=dict)
    failures: Dict[int, ProcessFailure] = field(default_factory=dict)
    error_type: ErrorType = ErrorType.NONE

    def is_failed(self) -> bool:
        return self.state == WorkerState.FAILED


class ElasticAgent(abc.ABC):
    r"""
    Agent process responsible for managing one or more worker processes.
    The worker processes are assumed to be regular distributed PyTorch scripts.
    When the worker process is created by the agent, the agent provides the
    necessary information for the worker processes to properly initialize
    a torch process group.

    The exact deployment topology and ratio of agent-to-worker is dependent
    on the specific implementation of the agent and the user's job placement
    preferences. For instance, to run a distributed training job on GPU with
    8 trainers (one per GPU) one can:

    1. Use 8 x single GPU instances, place an agent per instance, managing
       1 worker per agent.
    2. Use 4 x double GPU instances, place an agent per instance, managing
       2 workers per agent.
    3. Use 2 x quad GPU instances, place an agent per instance, managing
       4 workers per agent.
    4. Use 1 x 8 GPU instance, place an agent per instance, managing
       8 workers per agent.

    Usage
    ::

     group_result = agent.run()
      if group_result.is_failed():
        # workers failed
        failure = group_result.failures[0]
        log.exception(f"worker 0 failed with exit code : {failure.exit_code}")
      else:
        return group_result.return_values[0] # return rank 0's results

    """

    @abc.abstractmethod
    def run(self, role: str = DEFAULT_ROLE) -> Optional[RunResult]:
        """
        Runs the agent, retrying the worker group on failures unless
            user failure

        Returns:
            The result of the execution, containing the return values or
            failure details for each worker mapped by the worker's global rank.

        Raises:
            Exception - any other failures NOT related to worker process
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_worker_group(self, role: str = DEFAULT_ROLE) -> WorkerGroup:
        """
        Returns:
            The ``WorkerGroup`` for the given ``role``.
            Note that the worker group is a mutable object and hence in a
            multi-threaded/process environment it may change state.
            Implementors are encouraged (but not required) to return
            a defensive read-only copy.
        """
        raise NotImplementedError()


class SimpleElasticAgent(ElasticAgent):
    """
    An ``ElasticAgent`` that manages workers (``WorkerGroup``)
    for a single ``WorkerSpec`` (e.g. one particular type of worker role).
    """

    def __init__(self, spec: WorkerSpec, exit_barrier_timeout: float = 300):
        self._worker_group = WorkerGroup(spec)
        self._restart_count = 0
        self._store: Optional[Store] = None
        self._exit_barrier_timeout = exit_barrier_timeout
        self._total_execution_time = 0

    def get_worker_group(self, role: str = DEFAULT_ROLE) -> WorkerGroup:
        return self._worker_group

    @abc.abstractmethod
    def _start_workers(self, worker_group: WorkerGroup) -> Dict[int, Any]:
        r"""
        Starts ``worker_group.spec.local_world_size`` number of workers
        according to worker spec for the worker group .

        Returns a map of ``local_rank`` to worker ``id``.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _stop_workers(self, worker_group: WorkerGroup) -> None:
        r"""
        Stops all workers in the given worker group. Implementors
        must deal with workers in all states defined by ``WorkerState``.
        That is, it must gracefully handle stopping non-existent workers,
        unhealthy (stuck) workers, etc.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _monitor_workers(self, worker_group: WorkerGroup) -> RunResult:
        r"""
        Checks on the workers for the ``worker_group`` and returns
        the new state of the worker group.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _shutdown(self, death_sig: signal.Signals = signal.SIGTERM) -> None:
        """
        Cleans up any resources that were allocated during the agent's work.

        Args:
            death_sig: Signal to send to the child process, SIGTERM is default
        """
        raise NotImplementedError()

    def _rendezvous(self, worker_group: WorkerGroup) -> None:
        r"""
        Runs rendezvous for the workers specified by worker spec.
        Assigns workers a new global rank and world size.
        Updates the rendezvous store for the worker group.
        """

        spec = worker_group.spec

        store, group_rank, group_world_size = spec.rdzv_handler.next_rendezvous()
        self._store = store

        worker_info = worker_registry.get_worker_info(spec.framework, store, group_rank, group_world_size, spec)
        worker_group.store = store
        worker_group.group_rank = group_rank
        worker_group.group_world_size = group_world_size

        if group_rank == 0:
            set_master_addr_port(store, spec.master_addr, spec.master_port)

        workers = worker_registry.create_workers(spec.framework, store, worker_info)
        worker_group.workers = workers

    def _initialize_workers(self, worker_group: WorkerGroup) -> None:
        r"""
        Starts a fresh set of workers for the worker_group.
        Essentially a rendezvous followed by a start_workers.

        The caller should first call ``_stop_workers()`` to stop running workers
        prior to calling this method.

        Optimistically sets the state of the worker group that
        just started as ``HEALTHY`` and delegates the actual monitoring
        of state to ``_monitor_workers()`` method
        """
        role = worker_group.spec.role
        log.info(f"[{role}] Rendezvous'ing worker group")

        # TODO after stopping workers, wait at least monitor_interval*2 for
        # workers on different nodes to fail on a collective op before waiting
        # on the rdzv barrier, this way we ensure that nodes enter rdzv
        # at around the same time and reduce false positive rdzv timeout errors
        self._rendezvous(worker_group)

        log.info(f"[{role}] Starting worker group")
        worker_ids = self._start_workers(worker_group)
        for local_rank, w_id in worker_ids.items():
            worker = worker_group.workers[local_rank]
            worker._id = w_id

        worker_group.state = WorkerState.HEALTHY

    def _restart_workers(self, worker_group: WorkerGroup) -> None:
        """
        Restarts (stops, rendezvous, starts) all local workers in the group.
        """

        role = worker_group.spec.role
        log.info(f"[{role}] Stopping worker group")
        self._stop_workers(worker_group)
        worker_group.state = WorkerState.STOPPED
        self._initialize_workers(worker_group)

    def run(self, role: str = DEFAULT_ROLE) -> Optional[RunResult]:
        start_time = time.monotonic()
        shutdown_called: bool = False
        try:
            result = self._invoke_run(role)
            return result
        except SignalException as e:
            log.warning(f"Received {e.sigval} death signal, shutting down workers")
            self._shutdown(e.sigval)
            shutdown_called = True
            return None
        finally:
            if not shutdown_called:
                self._shutdown()
            # record the execution time in case there were any exceptions during run.
            self._total_execution_time = int(time.monotonic() - start_time)

    def _get_worker_state(self, worker: Worker, result: RunResult) -> str:
        failure = result.failures.get(worker.get_id())
        if result.state in {WorkerState.UNHEALTHY, WorkerState.FAILED} and not failure:
            # The worker got terminated by the torchelastic agent via SIGTERM signal
            return "TERMINATED"
        elif failure or worker.get_id() in result.return_values:
            return result.state.value
        else:
            raise ValueError(f"Unknow worker: {worker.get_id()}")

    def _invoke_run(self, role: str = DEFAULT_ROLE) -> RunResult:
        # NOTE: Restart policy applied to all roles

        spec = self._worker_group.spec
        role = spec.role

        log.info(
            f"[{role}] starting workers for entrypoint: {spec.get_entrypoint_name()}"
        )

        self._initialize_workers(self._worker_group)
        monitor_interval = spec.monitor_interval
        rdzv_handler = spec.rdzv_handler

        while True:
            assert self._worker_group.state != WorkerState.INIT
            time.sleep(monitor_interval)

            run_result = self._monitor_workers(self._worker_group)
            state = run_result.state
            self._worker_group.state = state

            if state == WorkerState.SUCCEEDED:
                log.info(
                    f"[{role}] worker group successfully finished."
                    f" Waiting {self._exit_barrier_timeout} seconds for other agents to finish."
                )
                self._exit_barrier()
                return run_result
            elif state in {WorkerState.UNHEALTHY, WorkerState.FAILED}:
                self._restart_count += 1
                if run_result.error_type == ErrorType.INFRA_FAILURE:
                    self._restart_workers(self._worker_group)
                elif run_result.error_type == ErrorType.USER_FAILURE:
                    self._stop_workers(self._worker_group)
                    rdzv_handler.shutdown()
                    return run_result
                else:
                    self._stop_workers(self._worker_group)
                    self._worker_group.state = WorkerState.FAILED
                    self._exit_barrier()
                    return run_result
            elif state == WorkerState.HEALTHY:
                # membership changes do not count as retries
                num_nodes_waiting = rdzv_handler.num_nodes_waiting()
                group_rank = self._worker_group.group_rank
                if num_nodes_waiting > 0:
                    log.info(
                        f"[{role}] Detected {num_nodes_waiting} "
                        f"new nodes from group_rank={group_rank}; "
                        f"will restart worker group"
                    )
                    self._restart_workers(self._worker_group)
            else:
                raise Exception(f"[{role}] Worker group in {state.name} state")

    def _exit_barrier(self):
        """
        Wait for ``exit_barrier_timeout`` seconds for all agents to finish
        executing their local workers (either successfully or not). This
        acts as a safety guard against user scripts that terminate at different
        times. This barrier keeps the agent process alive until all workers finish.
        """
        log.info(
            f"Local worker group finished ({self._worker_group.state}). "
            f"Waiting {self._exit_barrier_timeout} seconds for other agents to finish"
        )
        start = time.time()
        try:
            store_util.barrier(
                self._store,
                self._worker_group.group_rank,
                self._worker_group.group_world_size,
                key_prefix=_TERMINAL_STATE_SYNC_ID,
                barrier_timeout=self._exit_barrier_timeout,
            )
            log.info(
                f"Done waiting for other agents. Elapsed: {time.time() - start} seconds"
            )
        except SignalException as e:
            log.warn(f"Got termination signal: {e.sigval}")
            raise
        except Exception:
            log.exception(
                f"Error waiting on exit barrier. Elapsed: {time.time() - start} seconds"
            )
