import unittest
import uuid
from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch, MagicMock
import sys

from lattice.elastic.worker.api import (
    WorkerInfo,
    Worker,
    WorkerSpec,
    _RoleInstanceInfo,
    _determine_global_ranks,
    _determine_role_ranks,
    _share_and_gather,
    _get_ranks,
)

from lattice.elastic.rendezvous import RendezvousParameters
from lattice.elastic.rendezvous.etcd_server import EtcdServer
from lattice.elastic.rendezvous.etcd_rendezvous import create_rdzv_handler


class Store:
    def __init__(self):
        pass


# Classes to test that the `Role` attribute is working correctly
@dataclass
class RoleWorkerInfo(WorkerInfo):
    local_world_size: int = 1
    world_size: int = 1
    worker_global_ids: List[int] = field(default_factory=list)
    role_world_size: int = 1
    role_ranks: List[int] = field(default_factory=list)


class RoleWorker(Worker):
    """
    A dummy worker that uses the role attribute
    """
    def __init__(self, role, config):
        super().__init__(role, config)

        self.required_vars = [
            # Rank and world size of processes running on this node
            'LOCAL_WORLD_SIZE',
            'LOCAL_RANK',
            # Rank and world size among ALL processes participating in this job
            'GLOBAL_WORLD_SIZE',
            'GLOBAL_RANK',
            # Rank and world size among all workers with the same role
            'ROLE_WORLD_SIZE'
            'ROLE_RANK',
        ]


def get_role_worker_info(
    store: Store, group_rank: int, group_world_size: int, spec: WorkerSpec
) -> RoleWorkerInfo:
    role_infos, world_size, worker_global_ids = _determine_global_ranks(store, group_rank, group_world_size, spec)

    my_role_info = role_infos[group_rank]
    role_world_size, role_ranks = _determine_role_ranks(role_infos, my_role_info)

    return RoleWorkerInfo(
        framework=spec.framework,
        role=spec.role,
        local_world_size=spec.local_world_size,
        world_size=world_size,
        worker_global_ids=worker_global_ids,
        role_world_size=role_world_size,
        role_ranks=role_ranks
    )


def create_role_worker(
    store: Store, worker_info: RoleWorkerInfo
) -> List[RoleWorkerInfo]:
    workers = []
    for ind in range(worker_info.local_world_size):
        worker_config = {
            "LOCAL_WORLD_SIZE": worker_info.local_world_size,
            "LOCAL_RANK": str(ind),
            "GLOBAL_WORLD_SIZE": str(worker_info.world_size),
            "GLOBAL_RANK": str(worker_info.worker_global_ids[ind]),
            "ROLE_WORLD_SIZE": str(worker_info.role_world_size),
            "ROLE_RANK": str(worker_info.role_ranks[ind])
        }
        worker = RoleWorker(worker_info, worker_config)
        worker.set_id(worker_info.worker_global_ids[ind])
        workers.append(worker)

    return workers


entrypoint_cmd = 'env'


class WorkerCreationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._etcd_server = EtcdServer()
        cls._etcd_server.start()
        cls._port = cls._etcd_server.get_port()
        return super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._etcd_server.stop()
        return super().tearDownClass()

    @classmethod
    def getPort(cls):
        return cls._port

    def _get_worker_spec(
        self,
        role='default',
        framework='role_based',
        local_world_size=8,
        monitor_interval=0.5
    ) -> WorkerSpec:
        run_id = str(uuid.uuid4().int)
        port = WorkerCreationTest.getPort()
        endpoint = "127.0.0.1"
        port = str(port)
        rdzv_params = RendezvousParameters(
            backend="etcd",
            endpoint=endpoint,
            port=port,
            run_id=run_id,
            min_nodes=1,
            max_nodes=1,
            rank=0
        )
        rdzv_handler = create_rdzv_handler(rdzv_params)
        spec = WorkerSpec(
            framework=framework,
            role=role,
            local_world_size=local_world_size,
            entrypoint=entrypoint_cmd,
            rdzv_handler=rdzv_handler,
            monitor_interval=monitor_interval
        )

        return spec

    def test_get_ranks(self):
        role_infos = [
            _RoleInstanceInfo("parameter_server", 0, 4),
            _RoleInstanceInfo("trainer", 1, 1),
            _RoleInstanceInfo("trainer", 2, 2),
            _RoleInstanceInfo("trainer", 3, 3),
            _RoleInstanceInfo("parameter_server", 4, 5),
        ]
        total_sum, ranks = _get_ranks(role_infos, 0, 0, len(role_infos))
        self.assertEqual(15, total_sum)
        self.assertEqual([0, 1, 2, 3], list(ranks))

    def test_assign_worker_ranks(self):
        role_infos = [
            _RoleInstanceInfo("parameter_server", 0, 4),
            _RoleInstanceInfo("trainer", 1, 1),
            _RoleInstanceInfo("trainer", 2, 2),
            _RoleInstanceInfo("trainer", 3, 3),
            _RoleInstanceInfo("parameter_server", 4, 5),
        ]
        num_agents = len(role_infos)
        with patch("lattice.elastic.worker.api._share_and_gather", return_value=role_infos):
            self.verify_worker_ranks(
                role_infos[0], num_agents, [0, 1, 2, 3], [0, 1, 2, 3]
            )
            self.verify_worker_ranks(role_infos[1], num_agents, [4], [0])
            self.verify_worker_ranks(role_infos[2], num_agents, [5, 6], [1, 2])
            self.verify_worker_ranks(
                role_infos[3], num_agents, [7, 8, 9], [3, 4, 5])

    def verify_worker_ranks(
        self, agent_config, total_agents, expected_global_ids, expected_role_ranks
    ):
        role, agent_rank, local_world_size = (
            agent_config.role,
            agent_config.rank,
            agent_config.local_world_size,
        )
        spec = self._get_worker_spec(
            role=role,
            local_world_size=local_world_size
        )
        role_worker_info = get_role_worker_info(
            None, agent_rank, total_agents, spec)
        workers = create_role_worker(None, role_worker_info)
        self.assertEqual(
            expected_global_ids, [worker.get_id() for worker in workers]
        )
        self.assertEqual(expected_role_ranks, [
                            int(worker.get_config_value('ROLE_RANK')) for worker in workers])

    @patch("lattice.elastic.utils.store.synchronize")
    def test_share_and_gather(self, sync_mock):
        # when the state is unknown we exit immediately; no retries
        spec = self._get_worker_spec()
        expected_agent_infos = [
            _RoleInstanceInfo("trainer", 0, 10),
            _RoleInstanceInfo("trainer", 1, 10),
            _RoleInstanceInfo("validator", 2, 10),
        ]

        sync_mock.return_value = [obj.serialize()
                                  for obj in expected_agent_infos]
        mm = MagicMock()
        print("MM TYPE", type(mm), file=sys.stderr)
        result = _share_and_gather(MagicMock(), 1, 3, spec)
        sync_mock.assert_called_once()
        for expected_role_info, actual_role_info in zip(expected_agent_infos, result):
            self.assertEqual(expected_role_info.role, actual_role_info.role)
            self.assertEqual(expected_role_info.rank, actual_role_info.rank)
            self.assertEqual(
                expected_role_info.local_world_size, actual_role_info.local_world_size
            )
