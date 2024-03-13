from unittest import mock
from lattice_addons.state import (
    PicklableDict, PicklableWrapper, LocalCheckpoint,
    LocalCheckpointManager, LocalCheckpointCollectionManager,
    RemoteCheckpoint, RemoteCheckpointCollectionManager,
    CheckpointSetting, CheckpointCollectionSetting,
    S3Checkpoint, S3CheckpointCollectionManager,
    CHECKPOINT_TYPE, CHECKPOINT_CONFIG
)

from lattice_addons.state.distributed.utils import CheckpointMessage, RequestType

# Import internal components
from lattice_addons.state.ckpt_manager import (
    LocalCheckpointSaver, LocalCheckpointLoader, LocalCheckpointDeleter,
    RemoteCheckpointSaver, RemoteCheckpointLoader, RemoteCheckpointDeleter,
    S3CheckpointSaver, S3CheckpointLoader,
)

import io
import dill
import os
import tempfile
from pathlib import Path
import copy
import pytest
import zmq
from time import sleep
import multiprocessing as mp

from typing import List, Dict, Any
from unittest.mock import MagicMock, patch
import boto3
import botocore


def test_create_local_ckpt():
    # Registered types
    obj = PicklableDict(k1=3)
    _ = LocalCheckpoint(obj, '')
    _ = LocalCheckpoint(PicklableDict, '')

    # Non-registered types
    with pytest.raises(KeyError):
        _ = LocalCheckpoint(dict, '')


def test_local_ckpt_processors_for_picklable_dict():
    obj = PicklableDict(k1=3)

    path = Path(tempfile.mkdtemp()) / 'obj'

    ckpt = LocalCheckpointSaver.invoke(obj, str(path))
    assert ckpt.exists()

    resumed_obj = LocalCheckpointLoader.invoke(ckpt)
    assert resumed_obj == obj
    assert type(resumed_obj) == type(obj)

    LocalCheckpointDeleter.invoke(ckpt)
    assert not ckpt.exists()


def test_local_ckpt_processors_for_picklable_obj():
    data = [1, 2, {'k1': 5}]
    obj = PicklableWrapper(data)

    path = Path(tempfile.mkdtemp()) / 'obj'

    ckpt = LocalCheckpointSaver.invoke(obj, str(path))
    assert ckpt.exists()

    resumed_obj = LocalCheckpointLoader.invoke(ckpt)

    assert type(resumed_obj) == type(obj)
    assert resumed_obj.wrapped == obj.wrapped


def test_local_ckpt_mgr_w_history():
    root = tempfile.mkdtemp()

    def scope1() -> PicklableDict:
        obj = PicklableDict(k1=3)

        mgr = LocalCheckpointManager('lcm', root)

        mgr.save(obj)
        return copy.deepcopy(obj)

    def scope2(obj: PicklableDict):
        mgr = LocalCheckpointManager('lcm', root)

        assert mgr.len() != 0
        assert obj == mgr.load()

    scope2(scope1())


def test_local_ckpt_mgr_for_raw_files():
    root = Path(tempfile.mkdtemp())

    ckpt_file = root / 'LocalCheckpointManager:lcm_000001.Picklable'
    with open(ckpt_file, 'w') as f:
        f.write("")

    ckpt_file = root / 'LocalCheckpointManager:lcm_000005.Picklable'
    with open(ckpt_file, 'w') as f:
        f.write("")

    # Invalid pattern
    ckpt_file = root / 'LocalCheckpoint:lcm_000005.Picklable'
    with open(ckpt_file, 'w') as f:
        f.write("")

    # Unregistered type
    ckpt_file = root / 'LocalCheckpointManager:lcm_000005.Dict'
    with open(ckpt_file, 'w') as f:
        f.write("")

    mgr = LocalCheckpointManager('lcm', str(root))
    assert mgr.len() == 2
    assert mgr._counter == 6


def test_local_ckpt_mgr_for_loading_failure():
    root = Path(tempfile.mkdtemp())

    ckpt_file = root / 'LocalCheckpointManager:lcm_000001.Picklable'
    with open(ckpt_file, 'w') as f:
        f.write("")

    ckpt_file = root / 'LocalCheckpointManager:lcm_000005.Picklable'
    with open(ckpt_file, 'w') as f:
        f.write("")

    mgr = LocalCheckpointManager('lcm', str(root))
    assert mgr.load() is None
    assert mgr.len() == 0


def test_local_ckpt_mgr_for_custom_saver():
    class NumList:
        def __init__(self, vals: List[int]) -> None:
            self.vals: List[int] = vals

    root = Path(tempfile.mkdtemp())
    mgr = LocalCheckpointManager('lcm', str(root))

    def saver(nums: NumList, path: str) -> LocalCheckpoint:
        with open(path, 'w') as f:
            f.writelines([str(v) for v in nums.vals])
        return LocalCheckpoint(nums, path)

    def loader(ckpt: LocalCheckpoint) -> NumList:
        vals = []
        with open(ckpt.path, 'r') as f:
            for line in f.readlines():
                vals.append(int(line))
        return NumList(vals)

    obj = NumList([1, 2, 3])
    with pytest.raises(KeyError):
        mgr.save(obj)

    LocalCheckpointSaver.register_handler(NumList, saver)
    mgr.save(obj)

    LocalCheckpointLoader.register_handler(NumList, loader)
    mgr.load()


def test_local_ckpt_mgr_checks_permissions():
    root = Path(tempfile.mkdtemp())

    # Set temp file to read-only
    root.chmod(0o444)
    mgr = None
    with pytest.raises(PermissionError):
        mgr = LocalCheckpointManager('lcm', str(root))

    assert mgr is None


def test_local_ckpt_coll_mgr_w_history():
    root = tempfile.mkdtemp()

    def scope1() -> Dict[str, PicklableDict]:
        mgr = LocalCheckpointCollectionManager('lccm', root)

        obj1 = PicklableDict(k1=3)
        obj2 = PicklableDict(k2=4)
        state = {'o1': obj1, 'o2': obj2}

        mgr.save(state)
        return copy.deepcopy(state)

    def scope2(objs: Dict[str, PicklableDict]):
        mgr = LocalCheckpointCollectionManager('lccm', root)

        assert mgr.len() != 0
        assert objs == mgr.load()

    scope2(scope1())


def test_local_ckpt_coll_mgr_for_raw_files():
    root = Path(tempfile.mkdtemp())

    ckpt = root / 'LocalCheckpointCollectionManager:lccm_000003'
    ckpt.mkdir()

    with open(ckpt / 'k1.Picklable', 'w') as f:
        f.write("")

    with open(ckpt / 'k2.Picklable', 'w') as f:
        f.write("")

    # A single file
    ckpt = root / 'LocalCheckpointCollectionManager:lccm_000004.Picklable'
    with open(ckpt, 'w') as f:
        f.write("")

    # Invalid pattern
    ckpt = root / 'LocalCheckpoint:lccm_000005'
    ckpt.mkdir()

    # Invalid checkpoint file name
    ckpt = root / 'LocalCheckpointCollectionManager:lccm_000006'
    ckpt.mkdir()

    with open(ckpt / 'k1', 'w') as f:
        f.write("")

    # Unregistered type
    ckpt = root / 'LocalCheckpointCollectionManager:lccm_000007'
    ckpt.mkdir()

    with open(ckpt / 'k1.Dict', 'w') as f:
        f.write("")

    mgr = LocalCheckpointCollectionManager('lccm', str(root))
    assert mgr.len() == 1
    assert mgr._counter == 4


def test_local_ckpt_coll_mgr_for_loading_failure():
    root = Path(tempfile.mkdtemp())

    ckpt = root / 'LocalCheckpointCollectionManager:lccm_000003'
    ckpt.mkdir()

    with open(ckpt / 'k1.Picklable', 'w') as f:
        f.write("")

    with open(ckpt / 'k2.Picklable', 'w') as f:
        f.write("")

    mgr = LocalCheckpointCollectionManager('lccm', str(root))
    assert mgr.load() is None
    assert mgr.len() == 0


def test_local_ckpt_coll_mgr_for_concurrency1():
    root = tempfile.mkdtemp()
    n_proc = 2

    acquired = mp.Value('i', 0)

    def fn(idx: int, b: mp.Barrier, a: mp.Value):
        mgr = LocalCheckpointCollectionManager('lccm', root)

        obj1 = PicklableDict(k1=3)
        obj2 = PicklableDict(k2=4)
        state = {'o1': obj1, 'o2': obj2}

        b.wait()  # type: ignore[attr-defined]
        mgr.save(state)

        if mgr.acquired:
            a.value += 1  # type: ignore[attr-defined]

        b.wait()  # type: ignore[attr-defined]

    proc = []
    barrier = mp.Barrier(n_proc)
    for i in range(n_proc):
        p = mp.Process(target=fn, args=(i, barrier, acquired))
        proc.append(p)
        p.start()

    for p in proc:
        p.join()
        assert p.exitcode == 0

    assert acquired.value == 1


def test_local_ckpt_coll_mgr_for_concurrency2():
    root = tempfile.mkdtemp()
    n_proc = 2

    acquired = mp.Value('i', 0)

    def fn(idx: int, b: mp.Barrier, a: mp.Value):
        mgr = LocalCheckpointCollectionManager('lccm', root)

        obj1 = PicklableDict(k1=3)
        obj2 = PicklableDict(k2=4)
        state = {'o1': obj1, 'o2': obj2}

        b.wait()  # type: ignore[attr-defined]
        mgr.save(state)

        if mgr.acquired:
            a.value += 1  # type: ignore[attr-defined]

        b.wait()  # type: ignore[attr-defined]
        if mgr.acquired:
            return
        else:
            sleep(0.1)

            mgr.save(state)
            if mgr.acquired:
                a.value += 1  # type: ignore[attr-defined]

    proc = []
    barrier = mp.Barrier(n_proc)
    for i in range(n_proc):
        p = mp.Process(target=fn, args=(i, barrier, acquired))
        proc.append(p)
        p.start()

    for p in proc:
        p.join()
        assert p.exitcode == 0

    assert acquired.value == 2


def test_local_ckpt_coll_mgr_checks_permissions():
    root = Path(tempfile.mkdtemp())

    # Set temp file to read-only
    root.chmod(0o444)
    mgr = None
    with pytest.raises(PermissionError):
        mgr = LocalCheckpointCollectionManager('lccm', str(root))

    assert mgr is None


def create_server_response_message(req_type: RequestType, job_id: str, uid: str, ckpt_name: str, body: Any) -> bytes:
    response_msg = CheckpointMessage(req_type, job_id, uid, ckpt_name, body)
    return response_msg.encode_message()


def test_create_remote_ckpt():
    obj = PicklableDict(k1=3)
    _ = RemoteCheckpoint(obj, '', '', '')
    _ = RemoteCheckpoint(PicklableDict, '', '', '')

    # Non-registered_types
    with pytest.raises(KeyError):
        _ = RemoteCheckpoint(3, '', '', '')

    with pytest.raises(KeyError):
        _ = RemoteCheckpoint(dict, '', '', '')


def test_remote_ckpt_processors_for_picklable_dict():
    JOB_ID = "test-job"
    UID = "RemoteCheckpointCollectionManager:rccm_000000"

    obj = PicklableDict(k1=3)

    key_name = "obj"

    with patch('zmq.Socket') as mock_socket:
        mock_socket.recv.return_value = b'ACK'
        ckpt = RemoteCheckpointSaver.invoke(obj, mock_socket, JOB_ID, UID, key_name)

        response_msg = CheckpointMessage(RequestType.LIST, '', '', '', {UID: ['obj.Picklable']}).encode_message()
        mock_socket.recv.return_value = response_msg
        assert ckpt.exists(mock_socket)

    with patch('zmq.Socket') as mock_socket:
        byte_buffer = io.BytesIO()
        dill.dump(obj, byte_buffer)
        response_msg = CheckpointMessage(RequestType.LOAD, JOB_ID, UID, "obj", byte_buffer.getvalue()).encode_message()
        mock_socket.recv.return_value = response_msg

        resumed_obj = RemoteCheckpointLoader.invoke(ckpt, mock_socket)
        assert resumed_obj == obj
        assert type(resumed_obj) == type(obj)

    with patch('zmq.Socket') as mock_socket:
        mock_socket.recv.return_value = b'ACK'
        RemoteCheckpointDeleter.invoke(ckpt, mock_socket)

        response_msg = CheckpointMessage(RequestType.LIST, '', '', '', {UID: []}).encode_message()
        mock_socket.recv.return_value = response_msg
        assert not ckpt.exists(mock_socket)


def test_remote_collection_ckpt_mgr_w_history():
    JOB_ID = "test-job"
    UID = "RemoteCheckpointCollectionManager:rccm_000000"

    ckpt_service_endpoint = 'localhost'
    ckpt_service_port = '5555'

    obj1 = PicklableDict(k1=3)
    obj2 = PicklableDict(k2=4)

    def side_effects() -> List[bytes]:
        # This describes all of the expected messages that would be returned from the server and mocks them
        # when zmq.Socket.recv is called
        mocked_responses = []
        # Expected messages on socket for scope 1
        scope1_validate_response = create_server_response_message(RequestType.PING,
                                                                  job_id=JOB_ID, uid='',
                                                                  ckpt_name='',
                                                                  body=b'ACK')
        scope1_discover_response_body = {}
        scope1_discover_response = create_server_response_message(RequestType.LIST,
                                                                  job_id=JOB_ID,
                                                                  uid=UID,
                                                                  ckpt_name='',
                                                                  body=scope1_discover_response_body)
        scope1_save_response_obj1 = b'ACK'
        scope1_save_response_obj2 = b'ACK'

        # Messages that will be read from socket for scope1
        mocked_responses.append(scope1_validate_response)
        mocked_responses.append(scope1_discover_response)
        mocked_responses.append(scope1_save_response_obj1)
        mocked_responses.append(scope1_save_response_obj2)

        # Expected messages on socket for scope 2
        scope2_validate_response = create_server_response_message(RequestType.PING,
                                                                  job_id=JOB_ID,
                                                                  uid='',
                                                                  ckpt_name='',
                                                                  body=b'ACK')
        scope2_discover_response_body = {UID: ['o1.Picklable', 'o2.Picklable']}
        scope2_discover_response = create_server_response_message(RequestType.LIST,
                                                                  job_id=JOB_ID,
                                                                  uid=UID,
                                                                  ckpt_name='',
                                                                  body=scope2_discover_response_body)

        buffer = io.BytesIO()
        dill.dump(obj1, buffer)
        scope2_load_response_obj1 = create_server_response_message(RequestType.LOAD,
                                                                   job_id=JOB_ID,
                                                                   uid=UID,
                                                                   ckpt_name='o1',
                                                                   body=buffer.getvalue())

        buffer = io.BytesIO()
        dill.dump(obj2, buffer)
        scope2_load_response_obj2 = CheckpointMessage(RequestType.LOAD,
                                                      job_id=JOB_ID,
                                                      uid=UID,
                                                      ckpt_name='o2',
                                                      body=buffer.getvalue()).encode_message()

        # Messages that will be read from socket for scope 2
        mocked_responses.append(scope2_validate_response)
        mocked_responses.append(scope2_discover_response)
        mocked_responses.append(scope2_load_response_obj1)
        mocked_responses.append(scope2_load_response_obj2)

        return mocked_responses

    # Functions testing the scope of checkpoints
    def scope1() -> Dict[str, PicklableDict]:
        rccm = RemoteCheckpointCollectionManager('rccm', JOB_ID, ckpt_service_endpoint, ckpt_service_port)

        state = {'o1': obj1, 'o2': obj2}

        rccm.save(state)
        return copy.deepcopy(state)

    def scope2(objs: Dict[str, PicklableDict]) -> None:
        rccm = RemoteCheckpointCollectionManager('rccm', JOB_ID, ckpt_service_endpoint, ckpt_service_port)

        assert rccm.len() != 0
        assert objs == rccm.load()

    with patch.object(zmq.Socket, 'recv', side_effect=side_effects()), \
         patch.object(zmq.Socket, 'send', side_effects=[0, 0, 0, 0, 0, 0, 0]):
        scope2(scope1())


def test_default_global_ckpt_setting():
    cfg = CheckpointSetting()

    _ = cfg.ckpt_type('ckpt_mgr', **cfg.ckpt_config)


def test_custom_global_ckpt_setting():
    root = tempfile.mkdtemp()

    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = f'root={root}'

    cfg = CheckpointSetting()
    mgr = cfg.ckpt_type('ckpt_mgr', **cfg.ckpt_config)

    assert isinstance(mgr, LocalCheckpointManager)
    assert mgr._root == root


def test_invalid_custom_global_ckpt_setting():
    JOB_ID = "test-job"

    # Test for local checkpoint settings
    root = tempfile.mkdtemp()

    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = f'rx={root}'  # Invalid config

    with pytest.raises(Exception):
        _ = CheckpointSetting()

    # Test for remote checkpoint settings
    ckpt_service_endpoint = 'localhost'
    ckpt_service_port = '5555'

    os.environ[CHECKPOINT_TYPE] = 'remote'
    os.environ[CHECKPOINT_CONFIG] = \
        f'jsb_id={JOB_ID},ckpt_service_endpoint={ckpt_service_endpoint},ckpt_service_port={ckpt_service_port}'

    with pytest.raises(Exception):
        _ = CheckpointCollectionSetting()


def test_default_global_ckpt_coll_setting():
    cfg = CheckpointCollectionSetting()

    _ = cfg.ckpt_type('ckpt_mgr', **cfg.ckpt_config)


def test_custom_global_ckpt_coll_setting():
    root = tempfile.mkdtemp()

    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = f'root={root}'

    cfg = CheckpointCollectionSetting()
    mgr = cfg.ckpt_type('ckpt_mgr', **cfg.ckpt_config)

    assert isinstance(mgr, LocalCheckpointCollectionManager)
    assert not isinstance(mgr, LocalCheckpointManager)
    assert mgr._root == root


def test_create_s3_ckpt():
    obj = PicklableDict(k1=3)
    _ = S3Checkpoint(obj, '', '', '', '')
    _ = S3Checkpoint(PicklableDict, '', '', '', '')

    # Non-registered_types
    with pytest.raises(KeyError):
        _ = S3Checkpoint({'3': 3}, '', '', '', '')

    with pytest.raises(KeyError):
        _ = S3Checkpoint(dict, '', '', '', '')


def test_s3_ckpt_processors_for_picklable_dict():

    mock_s3_client = MagicMock()
    boto3.client = MagicMock(return_value=mock_s3_client)

    mock_s3_client.head_bucket.return_value = {}
    mock_s3_client.head_object.return_value = {}
    mock_s3_client.put_object.return_value = {}

    BUCKET_NAME = "test-bucket"
    JOB_ID = "test-job"
    UID = "test_uid"
    obj = PicklableDict(k1=3)
    key_name = "obj"

    ckpt = S3CheckpointSaver.invoke(obj, BUCKET_NAME, JOB_ID, UID, key_name)
    byte_buffer = io.BytesIO()
    dill.dump(obj, byte_buffer)

    body = io.BytesIO(byte_buffer.getvalue())
    streaming_body = botocore.response.StreamingBody(raw_stream=body, content_length=len(body.getbuffer()))
    mock_s3_client.get_object.return_value = {'Body': streaming_body}

    resumed_obj = S3CheckpointLoader.invoke(ckpt)

    assert resumed_obj == obj
    assert type(resumed_obj) == type(obj)


@mock.patch('lattice_addons.state.util.S3CheckpointHelper.ping')
@mock.patch('lattice_addons.state.util.S3CheckpointHelper.list')
@mock.patch('lattice_addons.state.util.S3CheckpointHelper.save')
@mock.patch('lattice_addons.state.util.S3CheckpointHelper.load')
def test_s3_collection_ckpt_mgr(mock_load, mock_save, mock_list, mock_ping):

    mock_ping.return_value = True
    mock_list.side_effect = [{}, {'S3CheckpointCollectionManager:smg_000000': ['o1.Picklable', 'o2.Picklable']}]

    obj1 = PicklableDict(k1=3)
    obj2 = PicklableDict(k2=4)

    buffer1 = io.BytesIO()
    buffer2 = io.BytesIO()
    dill.dump(obj1, buffer1)
    dill.dump(obj2, buffer2)
    mock_load.side_effect = [buffer1.getvalue(), buffer2.getvalue()]

    ROOT = "s3://test-bucket/test-job/"
    UID = "smg"

    def scope1() -> Dict[str, PicklableDict]:
        mock_list.return_value = {}
        mgr = S3CheckpointCollectionManager(UID, ROOT)

        state = {'o1': obj1, 'o2': obj2}

        mgr.save(state)
        return copy.deepcopy(state)

    def scope2() -> Dict[str, PicklableDict]:
        mgr = S3CheckpointCollectionManager(UID, ROOT)

        assert mgr.len() != 0
        return copy.deepcopy(mgr.load())

    assert scope1() == scope2()
