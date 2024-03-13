import logging
import os
import shutil
import signal
import tempfile
from typing import Any, Dict, Optional, Tuple

from lattice.elastic.agent.server.api import (
    RunResult,
    SimpleElasticAgent,
    WorkerGroup,
    WorkerSpec,
    WorkerState,
)
from lattice.elastic.multiprocessing.errors import ErrorType
from lattice.elastic.utils import macros
from lattice.elastic.multiprocessing import start_processes


logging.basicConfig(format='[%(levelname)s %(name)s] %(message)s', level=logging.INFO)


class LatticeAgent(SimpleElasticAgent):
    def __init__(
        self,
        spec: WorkerSpec,
        start_method='spawn',
        exit_barrier_timeout: float = 300,
        log_dir: Optional[str] = None,
        extra_env=None,
        monitor_config: Dict[str, str] = {}
    ):
        super().__init__(spec, exit_barrier_timeout)
        self._start_method = start_method
        self._pcontext: Optional[Any] = None
        rdzv_run_id = spec.rdzv_handler.get_run_id()
        self._log_dir = self._make_log_dir(log_dir, rdzv_run_id)
        self._extra_env = extra_env
        self._monitor_config = monitor_config

    def _make_log_dir(self, log_dir: Optional[str], rdzv_run_id: str):
        base_log_dir = log_dir or tempfile.mkdtemp(prefix="torchelastic_")
        os.makedirs(base_log_dir, exist_ok=True)
        dir = tempfile.mkdtemp(prefix=f"{rdzv_run_id}_", dir=base_log_dir)
        logging.info(f"log directory set to: {dir}")
        return dir

    def _start_workers(self, worker_group: WorkerGroup) -> Dict[int, Any]:
        spec = worker_group.spec
        store = worker_group.store
        assert store is not None

        args: Dict[int, Tuple] = {}
        envs: Dict[int, Dict[str, str]] = {}
        for worker_id, worker in enumerate(worker_group.workers):
            worker_env = worker.get_config()
            worker_env.update(
                {
                    'LATTICE_RUN_ID': spec.rdzv_handler.get_run_id(),
                    'NCCL_ASYNC_ERROR_HANDLING': str(1),
                }
            )
            if "OMP_NUM_THREADS" in os.environ:
                worker_env["OMP_NUM_THREADS"] = os.environ["OMP_NUM_THREADS"]
            if self._extra_env:
                worker_env.update(self._extra_env)
            envs[worker_id] = worker_env
            worker_args = list(spec.args)
            worker_args = macros.substitute(worker_args, str(worker_id))
            args[worker_id] = tuple(worker_args)

        # scaling events do not count towards restarts (gets same attempt #)
        # remove existing log dir if this restart is due to a scaling event
        attempt_log_dir = os.path.join(self._log_dir, f"attempt_{self._restart_count}")
        shutil.rmtree(attempt_log_dir, ignore_errors=True)
        os.makedirs(attempt_log_dir)

        assert spec.entrypoint is not None
        self._pcontext = start_processes(
            name=spec.role,
            entrypoint=spec.entrypoint,
            args=args,
            envs=envs,
            log_dir=attempt_log_dir,
            start_method=self._start_method,
            redirects=spec.redirects,
            tee=spec.tee,
            monitor_config=self._monitor_config
        )

        return self._pcontext.pids()

    def _stop_workers(self, worker_group: WorkerGroup) -> None:
        self._shutdown()

    def _monitor_workers(self, worker_group: WorkerGroup) -> RunResult:
        role = worker_group.spec.role
        worker_pids = {w._id for w in worker_group.workers}
        assert self._pcontext is not None
        pc_pids = set(self._pcontext.pids().values())
        if worker_pids != pc_pids:
            logging.error(
                f"[{role}] worker pids do not match process_context pids."
                f" Expected: {worker_pids}, actual: {pc_pids}"
            )
            return RunResult(state=WorkerState.UNKNOWN)

        result = self._pcontext.wait(0)
        if result:
            if result.is_failed():
                # map local rank failure to global rank
                worker_failures = {}
                for local_rank, failure in result.failures.items():
                    worker = worker_group.workers[local_rank]
                    worker_failures[worker.get_id()] = failure

                error_type = self._check_errors(worker_failures)
                return RunResult(
                    state=WorkerState.FAILED,
                    failures=worker_failures,
                    error_type=error_type
                )
            else:
                # copy ret_val_queue into a map with a global ranks
                workers_ret_vals = {}
                for local_rank, ret_val in result.return_values.items():
                    worker = worker_group.workers[local_rank]
                    workers_ret_vals[int(worker.get_id())] = ret_val
                return RunResult(
                    state=WorkerState.SUCCEEDED,
                    return_values=workers_ret_vals,
                )
        else:
            return RunResult(state=WorkerState.HEALTHY)

    def _is_infra_error(self, stderr):
        # TODO (JOHN) (p1): This error check is not very robust. Think of a better way
        return ("gloo" in stderr and ("Connection reset by peer" in stderr or "Connection closed by peer" in stderr)) \
            or "NCCL" in stderr

    def _check_errors(self, worker_failures):
        for rank, failure in worker_failures.items():
            if self._is_infra_error(failure.stderr):
                return ErrorType.INFRA_FAILURE

        return ErrorType.USER_FAILURE

    def _shutdown(self, death_sig: signal.Signals = signal.SIGTERM) -> None:
        if self._pcontext:
            self._pcontext.close(death_sig)
