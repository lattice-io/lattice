import functools
import json
import os
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, Union

import lattice.elastic.rendezvous as rdzv
import lattice.elastic.utils.store as store_util
from lattice.elastic.utils.store import (
    get_master_addr_port,
)
from lattice.elastic.utils.logging import get_logger
from lattice.elastic.multiprocessing import Std
from lattice.elastic.rendezvous.store import Store

log = get_logger()


class InvalidConfigError(Exception):
    def __init__(self):
        pass


@dataclass
class WorkerSpec:
    """
    Contains blueprint information about a particular type of worker.
    For a given role, there must only exist a single worker spec.
    Worker spec is expected to be homogenous across all nodes (machine),
    that is each node runs the same number of workers for a particular spec.

    Args:
        framework: the machine learning framework to use for this worker
        role: user-defined role for the workers with this spec
        local_world_size: number local workers to run
        fn: (deprecated use entrypoint instead)
        entrypoint: worker function or command
        args: arguments to pass to ``entrypoint``
        rdzv_handler: handles rdzv for this set of workers
        monitor_interval: monitor status of workers every ``n`` seconds
        master_port: fixed port to run the c10d store on rank 0
                     if not specified then will chose a random free port
        master_addr: fixed master_addr to run the c10d store on rank 0
                     if not specified then will chose hostname on agent rank 0
        redirects: redirect std streams to a file,
                   selectively redirect for a particular
                   local rank by passing a map
        tee: tees the specified std stream(s) to console + file,
             selectively tee for a particular local rank by passing a map,
             takes precedence over ``redirects`` settings.

    """

    framework: str
    role: str
    local_world_size: int
    rdzv_handler: rdzv.RendezvousHandler
    fn: Optional[Callable] = None
    # TODO @kiuk - make entrypoint a required field
    entrypoint: Union[str, None] = None
    args: Tuple = ()
    monitor_interval: float = 30.0
    master_port: Optional[int] = None
    master_addr: Optional[str] = None
    redirects: Union[Std, Dict[int, Std]] = Std.NONE
    # Default to tee stderr so we can look at errors
    tee: Union[Std, Dict[int, Std]] = Std.ERR

    def __post_init__(self):
        assert self.local_world_size > 0
        assert self.monitor_interval > 0

        if self.fn:
            warnings.warn(
                "WorkerSpec.fn will be deprecated,"
                " please use WorkerSpec.entrypoint instead",
                category=DeprecationWarning,
            )
            self.entrypoint = self.fn
        assert self.entrypoint

    def get_entrypoint_name(self):
        """
        If the entrypoint is a function (e.g. ``Callable``) returns its ``__qualname__``,
        else if the entrypoint is a binary (e.g. ``str``), returns the binary name.
        """
        if isinstance(self.entrypoint, str):
            return os.path.basename(self.entrypoint)
        else:
            assert self.entrypoint is not None
            return self.entrypoint.__qualname__


@dataclass
class WorkerInfo:
    framework: Optional[str] = None
    role: str = 'default'


@dataclass
class GenericWorkerInfo(WorkerInfo):
    local_world_size: int = 1
    world_size: int = 1
    # Generic worker has no concept of rank, but we still want
    # to give some unique global IDs to each worker
    worker_global_ids: List[int] = field(default_factory=list)


@dataclass
class PyTorchWorkerInfo(WorkerInfo):
    local_world_size: int = 1
    world_size: int = 1
    worker_global_ranks: List[int] = field(default_factory=list)


@dataclass
class PyTorchLightningWorkerInfo(PyTorchWorkerInfo):
    node_rank: int = 1


@dataclass
class TensorFlowWorkerInfo(WorkerInfo):
    pass


class Worker:
    def __init__(self, role: str, config: Dict = {}):
        """
        Represents a worker instance. Contrast this with ``WorkerSpec`` that
        represents the specifications of a worker. A ``Worker`` is created from
        a ``WorkerSpec``. A ``Worker`` is to a ``WorkerSpec`` as an object is to
        a class.
        """
        # ID represenets some unique identifier for this worker that is left
        # to implement depending on the type of worker
        # For example, for a PyTorchWorker, the ID will be set to its RANK
        self._id: int = -1
        self._local_id: int = -1

        self._role: str = role
        self._config: Dict = config
        self._required_vars: List = []

    def __str__(self):
        class_str = f'Role: {self._role}\n'
        class_str += 'Config:\n'
        for k, v in self._config.items():
            class_str += f'\t{k}: {v}\n'

        return class_str

    def get_id(self) -> int:
        return self._id

    def get_local_id(self) -> int:
        return self._local_id

    def get_role(self) -> str:
        return self._role

    def get_config(self) -> Dict:
        return self._config

    def set_id(self, id: int) -> None:
        self._id = id

    def set_local_id(self, local_id: int) -> None:
        self._local_id = local_id

    def get_config_value(self, key: str) -> str:
        return self._config[key]

    def set_config_value(self, key: str, value: str) -> None:
        self._config[key] = value

    def validate_config(self) -> None:
        missing_keys = []
        for key in self._required_vars:
            if key not in self._config:
                missing_keys.append(key)

        if missing_keys:
            log.error(f"Config not valid! Missing required env vars {missing_keys}")
            raise InvalidConfigError


class GenericWorker(Worker):
    def __init__(self, role, config):
        super().__init__(role, config)

        self._required_vars = []


class PyTorchWorker(Worker):
    def __init__(self, role, config):
        super().__init__(role, config)

        self._required_vars = [
            'LOCAL_RANK',
            'RANK',
            'WORLD_SIZE',
            'MASTER_ADDR',
            'MASTER_PORT',
        ]


class PyTorchLightningWorker(Worker):
    def __init__(self, role, config):
        super.__init__(role, config)

        self._required_vars = [
            'LOCAL_RANK',
            'RANK',
            'WORLD_SIZE',
            'MASTER_ADDR',
            'MASTER_PORT',
            'NODE_RANK',
            'LOCAL_WORLD_SIZE',
        ]


class TensorFlowWorker(Worker):
    def __init__(self, role, config):
        super.__init__(role, config)

        self._required_vars = [
            'TF_CONFIG'
        ]


class WorkerState(str, Enum):
    """
    State of the ``WorkerGroup``. Workers in a worker group change state as a unit.
    If a single worker in a worker group fails the entire set is considered
    failed::

      UNKNOWN - agent lost track of worker group state, unrecoverable
      INIT - worker group object created not yet started
      HEALTHY - workers running and healthy
      UNHEALTHY - workers running and unhealthy
      STOPPED - workers stopped (interruped) by the agent
      SUCCEEDED - workers finished running (exit 0)
      FAILED - workers failed to successfully finish (exit !0)


    A worker group starts from an initial ``INIT`` state,
    then progresses to ``HEALTHY`` or ``UNHEALTHY`` states,
    and finally reaches a terminal ``SUCCEEDED`` or ``FAILED`` state.

    Worker groups can be interrupted and temporarily put into ``STOPPED`` state
    by the agent. Workers in ``STOPPED`` state are scheduled to be restarted
    in the near future by the agent. Some examples of workers being put into
    ``STOPPED`` state are:

    1. Worker group failure|unhealthy observed
    2. Membership change detected

    When actions (start, stop, rdzv, retry, etc) on worker group fails
    and results in the action being partially applied to the worker group
    the state will be ``UNKNOWN``. Typically this happens on uncaught/unhandled
    exceptions during state change events on the agent. The agent is not
    expected to recover worker groups in ``UNKNOWN`` state and is better off
    self terminating and allowing the job manager to retry the node.
    """

    UNKNOWN = "UNKNOWN"
    INIT = "INIT"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    STOPPED = "STOPPED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

    @staticmethod
    def is_running(state: "WorkerState") -> bool:
        """
        Returns:
             True if the worker state represents workers still running
             (e.g. that the process exists but not necessarily healthy).
        """
        return state in {WorkerState.HEALTHY, WorkerState.UNHEALTHY}


class WorkerGroup:
    """
    Represents the set of ``Worker`` instances for the given ``WorkerSpec``
    managed by ``ElasticAgent``. Whether the worker group contains cross
    instance workers or not depends on the implementation of the agent.
    """

    __slots__ = ["spec", "workers", "store", "group_rank", "group_world_size", "state"]

    def __init__(self, spec: WorkerSpec):
        self.spec = spec
        self.workers = [Worker(role=self.spec.role) for _ in range(self.spec.local_world_size)]

        # assigned after rdzv
        self.store: Optional[Store] = None
        self.group_rank: Optional[int] = None
        self.group_world_size: Optional[int] = None

        self.state = WorkerState.INIT


class _RoleInstanceInfo:
    """
    The class is used by the agent to exchange the information with other agents.
    The information is used to determine the rank of the workers that agent
    manages in heterogeneous environments, where different agents can have
    different number of workers.
    """

    __slots__ = ["role", "rank", "local_world_size"]

    def __init__(self, role: str, rank: int, local_world_size: int):
        r"""

        Args:
            role (str): user-defined role for the workers with this spec
            rank (int): the rank of the agent
            local_world_size (int): number of local workers to run
        """

        self.role = role
        self.rank = rank
        self.local_world_size = local_world_size

    def serialize(self) -> bytes:
        dict_data = {
            "role": self.role,
            "rank": self.rank,
            "local_world_size": self.local_world_size,
        }
        return json.dumps(dict_data).encode(encoding="UTF-8")

    @staticmethod
    def deserialize(data: bytes):
        dict_data = json.loads(data.decode(encoding="UTF-8"))
        return _RoleInstanceInfo(
            dict_data["role"], dict_data["rank"], dict_data["local_world_size"]
        )

    @staticmethod
    def compare(obj1, obj2) -> int:
        if obj1.role == obj2.role:
            return obj1.rank - obj2.rank
        elif obj1.role > obj2.role:
            return 1
        else:
            return -1

    @staticmethod
    def find_role_boundaries(roles_infos: List, role: str) -> Tuple[int, int]:
        start_idx, end_idx = -1, -1
        for idx, role_info in enumerate(roles_infos):
            if role_info.role == role:
                if start_idx == -1:
                    start_idx = idx
                end_idx = idx
        return (start_idx, end_idx)


def _determine_global_ranks(
    store: Store, group_rank: int, group_world_size: int, spec: WorkerSpec
):
    role_infos = _share_and_gather(store, group_rank, group_world_size, spec)
    worker_world_size, worker_global_ranks = _get_ranks(role_infos, group_rank)

    return role_infos, worker_world_size, worker_global_ranks


def _get_ranks(
    role_infos: List[_RoleInstanceInfo],
    role_idx: int,
    start_idx: int = 0,
    end_idx: int = -1,
) -> Tuple[int, List[int]]:
    if end_idx == -1:
        end_idx = len(role_infos)
    prefix_sum = 0
    total_sum = 0
    for idx in range(start_idx, end_idx):
        if role_idx > idx:
            prefix_sum += role_infos[idx].local_world_size
        total_sum += role_infos[idx].local_world_size
    return (
        total_sum,
        list(range(prefix_sum, prefix_sum + role_infos[role_idx].local_world_size)),
    )


def _share_and_gather(
    store, group_rank: int, group_world_size: int, spec: WorkerSpec
) -> List:
    agent_role_info = _RoleInstanceInfo(
        spec.role, group_rank, spec.local_world_size
    )
    key_prefix = "torchelastic/role_info"
    agent_config_enc = agent_role_info.serialize()
    role_infos_bytes = store_util.synchronize(
        store, agent_config_enc, group_rank, group_world_size, key_prefix
    )
    role_infos = [
        _RoleInstanceInfo.deserialize(role_info_bytes)
        for role_info_bytes in role_infos_bytes
    ]
    return role_infos


def _determine_role_ranks(
    role_infos: List[_RoleInstanceInfo], my_role_info: _RoleInstanceInfo
):
    """
    Determines proper ranks for worker processes. The rank assignment
    is done according to the following algorithm:

    1. Each agent writes its configuration(group_rank, group_world_size
        , num_workers) to the common store.
    2. Each agent retrieves configuration for all agents
        and performs two level sort using role and rank.
    3. Determine the global rank: the global rank of the workers for the current
        agent is the offset of the infos array up to group_rank of the agent.
        The offset is computed as a sum of local_world_size of all agents that
        have rank less than the group_rank. The workers would have the ranks:
        [offset, offset+local_world_size)
    4. Determine the role rank: The role rank is determined using the algorithms
        in the point 3 with the exception that the offset is done from the first
        agent that has the same role as current one and has the minimum group rank.
    """

    role_infos = sorted(
        role_infos, key=functools.cmp_to_key(_RoleInstanceInfo.compare)
    )
    role_start_idx, role_end_idx = _RoleInstanceInfo.find_role_boundaries(
        role_infos, my_role_info.role
    )
    role_pos = next(
        idx
        for idx, role_info in enumerate(role_infos)
        if _RoleInstanceInfo.compare(role_info, my_role_info) == 0
    )
    role_world_size, role_ranks = _get_ranks(
        role_infos, role_pos, role_start_idx, role_end_idx + 1
    )

    return role_world_size, role_ranks


def get_generic_worker_info(
    store: Store, group_rank: int, group_world_size: int, spec: WorkerSpec
) -> WorkerInfo:
    _, world_size, worker_global_ids = _determine_global_ranks(store, group_rank, group_world_size, spec)

    return GenericWorkerInfo(
        role=spec.role,
        local_world_size=spec.local_world_size,
        world_size=world_size,
        worker_global_ids=worker_global_ids,
    )


def get_pytorch_worker_info(
    store: Store, group_rank: int, group_world_size: int, spec: WorkerSpec
) -> PyTorchWorkerInfo:
    _, worker_world_size, worker_global_ranks = _determine_global_ranks(store, group_rank, group_world_size, spec)

    return PyTorchWorkerInfo(
        role=spec.role,
        local_world_size=spec.local_world_size,
        world_size=worker_world_size,
        worker_global_ranks=worker_global_ranks,
    )


def get_pytorch_lightning_worker_info(store: Store, group_rank: int,
                                      group_world_size: int, spec: WorkerSpec) -> WorkerInfo:
    raise NotImplementedError()


def get_tensorflow_worker_info(store: Store, group_rank: int,
                               group_world_size: int, spec: WorkerSpec) -> WorkerInfo:
    raise NotImplementedError()


def create_generic_worker(store: Store, worker_info: WorkerInfo) -> List[Worker]:
    assert isinstance(worker_info, GenericWorkerInfo)
    # TODO(p2): Using assert statement instead of explicitly typing worker_info arg
    # because mypy kept throwing an error even though the types are inherited...
    workers: List[Worker] = []
    for ind in range(worker_info.local_world_size):
        # Generic worker so we don't assume any config is needed
        worker_config: Dict[str, str] = {}
        worker = GenericWorker(worker_info.role, worker_config)
        worker.set_id(worker_info.worker_global_ids[ind])
        worker.set_local_id(ind)
        workers.append(worker)

    return workers


def create_pytorch_workers(store: Store, worker_info: WorkerInfo) -> List[Worker]:
    assert isinstance(worker_info, PyTorchWorkerInfo)
    workers: List[Worker] = []
    master_addr, master_port = get_master_addr_port(store)

    for ind in range(worker_info.local_world_size):
        worker_config = {
            'LOCAL_RANK': str(ind),
            'RANK': str(worker_info.worker_global_ranks[ind]),
            'WORLD_SIZE': str(worker_info.world_size),
            'MASTER_ADDR': master_addr,
            'MASTER_PORT': str(master_port),
        }
        worker = PyTorchWorker(worker_info.role, worker_config)
        worker.set_id(worker_info.worker_global_ranks[ind])
        worker.set_local_id(ind)
        workers.append(worker)

    return workers


def create_pytorch_lightning_workers(store: Store, worker_info: WorkerInfo) -> List[Worker]:
    assert isinstance(worker_info, PyTorchLightningWorkerInfo)
    workers: List[Worker] = []
    master_addr, master_port = get_master_addr_port(store)

    for ind in range(worker_info.local_world_size):
        worker_config = {
            'LOCAL_RANK': str(ind),
            'RANK': str(worker_info.worker_global_ranks[ind]),
            'WORLD_SIZE': str(worker_info.world_size),
            'MASTER_ADDR': master_addr,
            'MASTER_PORT': str(master_port),
            # TODO: Rework assign worker ranks to get this info
            # 'NODE_RANK': worker_info.node_rank,
        }
        worker = PyTorchLightningWorker(worker_info.role, worker_config)
        workers.append(worker)

    return workers


def create_tensorflow_workers(store: Store, worker_info: WorkerInfo) -> List[Worker]:
    assert isinstance(worker_info, TensorFlowWorkerInfo)
    raise NotImplementedError()


WorkerInfoGatherer = Callable[[Store, int, int, WorkerSpec], WorkerInfo]
WorkerCreator = Callable[[Store, WorkerInfo], List[Worker]]


class WorkerCreatorRegistry:
    """Represents a registry of different ways to implement both gathering
        info for workers as well as how to create the workers using that info
    """

    _gather_info_registry: Dict[str, WorkerInfoGatherer]
    _create_worker_registry: Dict[str, WorkerCreator]

    def __init__(self) -> None:
        self._gather_info_registry = {}
        self._create_worker_registry = {}

    def register_info_gatherer(self, framework: str, gatherer: WorkerInfoGatherer) -> None:
        if framework in self._gather_info_registry:
            raise ValueError("Info gatherer already registered")

        self._gather_info_registry[framework] = gatherer

    def register_worker_creator(self, framework: str, creator: WorkerCreator) -> None:
        if framework in self._create_worker_registry:
            raise ValueError("Worker creator already registered")

        self._create_worker_registry[framework] = creator

    def get_worker_info(self, framework: str, store: Store, group_rank: int,
                        group_world_size: int, spec: WorkerSpec) -> WorkerInfo:
        info_gather_func = self._gather_info_registry[framework]
        return info_gather_func(store, group_rank, group_world_size, spec)

    def create_workers(self, framework: str, store: Store, worker_info: WorkerInfo) -> List[Worker]:
        create_worker_func = self._create_worker_registry[framework]
        return create_worker_func(store, worker_info)


worker_registry = WorkerCreatorRegistry()
