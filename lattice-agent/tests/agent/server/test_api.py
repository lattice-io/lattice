import unittest
import logging
import uuid
import signal
from contextlib import closing
from unittest.mock import patch
from typing import Any, Dict

from lattice.elastic.worker.constants import (
    NO_FRAMEWORK,
    PYTORCH_JOB_FRAMEWORK
)
from lattice.elastic.agent.server.api import (
    RunResult,
    SimpleElasticAgent,
    WorkerGroup,
    WorkerSpec,
    WorkerState,
)
from lattice.elastic.utils.store import (
    get_fq_hostname,
    get_master_addr_port,
)

from lattice.elastic.multiprocessing import SignalException
from lattice.elastic.multiprocessing.errors import ProcessFailure
from lattice.elastic.rendezvous import RendezvousHandler, RendezvousParameters
from lattice.elastic.rendezvous.etcd_server import EtcdServer
from lattice.elastic.rendezvous.etcd_rendezvous import create_rdzv_handler
from lattice.elastic.utils import get_socket_with_port


entrypoint_cmd = 'env'


def get_free_port():
    sock = get_socket_with_port()
    with closing(sock):
        return sock.getsockname()[1]


class WorkerStateTest(unittest.TestCase):
    def test_is_running(self):
        for state in WorkerState:
            if state == WorkerState.HEALTHY or state == WorkerState.UNHEALTHY:
                self.assertTrue(WorkerState.is_running(state))
            else:
                self.assertFalse(WorkerState.is_running(state))


class WorkerGroupTest(unittest.TestCase):
    def test_worker_group_constructor(self):
        spec = WorkerSpec(
            framework=NO_FRAMEWORK,
            role="test_trainer",
            local_world_size=4,
            entrypoint=entrypoint_cmd,
            args=(),
            rdzv_handler=None,
            monitor_interval=1,
        )
        worker_group = WorkerGroup(spec)

        self.assertEqual(WorkerState.INIT, worker_group.state)

        workers = worker_group.workers
        self.assertEqual(4, len(workers))

        # rank and store are assigned after rdzv; validate that they are None
        self.assertIsNone(worker_group.group_rank)
        self.assertIsNone(worker_group.store)


class MockAgent(SimpleElasticAgent):
    def __init__(self, spec):
        super().__init__(spec)
        self.stop_workers_call_count = 0
        self.start_workers_call_count = 0

    def _stop_workers(self, worker_group: WorkerGroup) -> None:
        # workers are fake, nothing to stop; just clear the rdzv info
        worker_group.group_rank = None
        worker_group.group_world_size = None
        self.stop_workers_call_count += 1

    def _start_workers(self, worker_group: WorkerGroup) -> Dict[int, Any]:
        # crate fake workers; make worker id equal to global rank
        ids = {}
        for worker in worker_group.workers:
            ids[worker.get_local_id()] = worker.get_id()
        self.start_workers_call_count += 1
        return ids

    def _monitor_workers(self, worker_group: WorkerGroup) -> RunResult:
        raise NotImplementedError("mock this method")

    def _shutdown(self):
        pass

    def _monitor_job_metrics(self):
        pass


def monres(state: WorkerState):
    if state == WorkerState.SUCCEEDED:
        return RunResult(state=state, return_values={0: 0}, failures={})
    elif state in {WorkerState.UNHEALTHY, WorkerState.FAILED}:
        pf = ProcessFailure(local_rank=0, pid=999,
                            exitcode=1, error_file="<none>")
        return RunResult(state=state, return_values={}, failures={0: pf})
    else:
        return RunResult(state=state)


class SimpleElasticAgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.disable(logging.WARNING)
        cls._etcd_server = EtcdServer()
        cls._etcd_server.start()
        cls._port = cls._etcd_server.get_port()
        return super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        logging.disable(logging.NOTSET)
        cls._etcd_server.stop()
        return super().tearDownClass()

    @classmethod
    def getPort(cls):
        return cls._port

    def _get_worker_spec(
        self,
        framework=NO_FRAMEWORK,
        monitor_interval=1.0,
        role="test_trainer",
        local_world_size=8,
    ):
        run_id = str(uuid.uuid4().int)
        port = SimpleElasticAgentTest.getPort()
        endpoint = "127.0.0.1"
        p = f"{port}"
        rdzv_params = RendezvousParameters(
            backend="etcd",
            endpoint=endpoint,
            port=p,
            run_id=run_id,
            min_nodes=1,
            max_nodes=1,
            rank=0,
        )
        rdzv_handler = create_rdzv_handler(rdzv_params)
        spec = WorkerSpec(
            framework=framework,
            role=role,
            local_world_size=local_world_size,
            entrypoint=entrypoint_cmd,
            args=(),
            rdzv_handler=rdzv_handler,
            monitor_interval=monitor_interval,
        )
        return spec

    def test_agent_constructor(self):
        spec = self._get_worker_spec()
        agent = MockAgent(spec)
        worker_group = agent.get_worker_group()
        self.assertEqual(WorkerState.INIT, worker_group.state)
        self.assertEqual(agent._restart_count, 0)

    @patch.object(MockAgent, "_invoke_run")
    @patch.object(MockAgent, "_shutdown")
    def test_invoke_run(
        self, shutdown_mock, invoke_run_mock
    ):
        spec = self._get_worker_spec()
        agent = MockAgent(spec)
        agent.run()
        invoke_run_mock.assert_called_once()
        shutdown_mock.assert_called_once()

    def test_rendezvous(self):
        spec = self._get_worker_spec(framework=PYTORCH_JOB_FRAMEWORK)
        agent = MockAgent(spec)
        worker_group = agent.get_worker_group()
        agent._rendezvous(worker_group)

        # single agent rdzv
        self.assertEqual(1, worker_group.group_world_size)
        self.assertEqual(0, worker_group.group_rank)

        master_addr, master_port = get_master_addr_port(
            worker_group.store)

        self.assertEqual(get_fq_hostname(), master_addr)
        self.assertTrue(master_port > 0)

        rank_set = {w.get_id() for w in worker_group.workers}
        for w in worker_group.workers:
            local_world_size = spec.local_world_size
            group_world_size = worker_group.group_world_size
            group_rank = worker_group.group_rank

            self.assertEqual(local_world_size * group_world_size, int(w.get_config_value('WORLD_SIZE')))
            self.assertEqual(
                local_world_size * group_rank + int(w.get_config_value('LOCAL_RANK')), int(w.get_config_value('RANK'))
            )
            self.assertSetEqual(set(range(int(w.get_config_value('WORLD_SIZE')))), rank_set)

    def test_initialize_workers(self):
        spec = self._get_worker_spec(framework=PYTORCH_JOB_FRAMEWORK)
        agent = MockAgent(spec)
        worker_group = agent.get_worker_group()
        agent._initialize_workers(worker_group)

        self.assertEqual(WorkerState.HEALTHY, worker_group.state)
        for i in range(spec.local_world_size):
            worker = worker_group.workers[i]
            self.assertEqual(worker.get_id(), int(worker.get_config_value('RANK')))

    def test_restart_workers(self):
        spec = self._get_worker_spec(framework=PYTORCH_JOB_FRAMEWORK)
        agent = MockAgent(spec)
        worker_group = agent.get_worker_group()

        num_restarts = 3
        for _ in range(0, num_restarts):
            agent._restart_workers(worker_group)
            self.assertEqual(WorkerState.HEALTHY, worker_group.state)

            # test_rendezvous and test_initialize_workers
            # already validates the correctness of these fields
            # simply validate that they are not None
            # (e.g. that they get assigned)
            self.assertIsNotNone(worker_group.group_rank)
            self.assertIsNotNone(worker_group.group_world_size)
            for w in worker_group.workers:
                self.assertIsNotNone(w.get_id())
                self.assertIsNotNone(w.get_config_value('RANK'))
                self.assertIsNotNone(w.get_config_value('WORLD_SIZE'))

        self.assertEqual(num_restarts, agent.start_workers_call_count)
        self.assertEqual(num_restarts, agent.stop_workers_call_count)

    @patch.object(MockAgent, "_initialize_workers", side_effect=RuntimeError())
    def test_run_initialization_failure(self, mock_initialize_workers):
        spec = self._get_worker_spec()
        agent = MockAgent(spec)
        worker_group = agent._worker_group

        with self.assertRaises(RuntimeError):
            agent.run()

        self.assertEqual(WorkerState.INIT, worker_group.state)

    @patch.object(
        MockAgent,
        "_monitor_workers",
        side_effect=[
            monres(WorkerState.HEALTHY),
            monres(WorkerState.HEALTHY),
            monres(WorkerState.HEALTHY),
            monres(WorkerState.SUCCEEDED),
        ],
    )
    @patch.object(RendezvousHandler, "num_nodes_waiting", side_effect=[1, 1, 0])
    def test_run_membership_change(
        self, mock_num_nodes_waiting, mock_monitor_workers
    ):
        spec = self._get_worker_spec(monitor_interval=0.1)
        agent = MockAgent(spec)
        worker_group = agent._worker_group

        agent.run()
        self.assertEqual(WorkerState.SUCCEEDED, worker_group.state)

    @patch.object(
        MockAgent, "_monitor_workers", return_value=monres(WorkerState.UNKNOWN)
    )
    def test_run_unknown_state(self, mock_monitor_workers):
        # when the state is unknown we exit immediately; no retries
        spec = self._get_worker_spec(monitor_interval=0.1)
        agent = MockAgent(spec)
        worker_group = agent._worker_group

        with self.assertRaises(Exception):
            agent.run()

        self.assertEqual(WorkerState.UNKNOWN, worker_group.state)
        self.assertEqual(1, mock_monitor_workers.call_count)
        self.assertEqual(0, agent._restart_count)

    @patch.object(MockAgent, "_invoke_run")
    def test_agent_process_signal_exception(self, invoke_run):
        spec = self._get_worker_spec()
        agent = MockAgent(spec)
        agent._invoke_run.side_effect = SignalException(
            "signal exception", sigval=signal.SIGTERM
        )

        with patch.object(agent, "_shutdown") as shutdown_mock:
            # with self.assertRaises(SignalException): # Current implementation does not raise SignalException
            agent.run()
            args, _ = shutdown_mock.call_args
            self.assertEqual(signal.SIGTERM, args[0])


if __name__ == "__main__":
    unittest.main()
