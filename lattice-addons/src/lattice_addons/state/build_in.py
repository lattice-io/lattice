from pathlib import Path
from typing import Any
from .state_manager import State
from .ckpt_manager import (
    local_checkpoint_saver, local_checkpoint_loader, local_checkpoint_deleter,
    remote_checkpoint_saver, remote_checkpoint_loader, remote_checkpoint_deleter,
    s3_checkpoint_saver, s3_checkpoint_loader, s3_checkpoint_deleter,
)
from .distributed.utils import (
    RequestType,
    CheckpointMessage,
)
from .util import S3CheckpointHelper

import os
import dill
import io
import zmq


# Picklable
class Picklable(State):
    r""" States that can be serialized and deserialized using pickle. """

    def _is_picklable(self) -> bool:
        try:
            dill.dumps(self)
            return True
        except Exception:
            return False


class PicklableDict(Picklable, dict):
    r""" Dictionary-based states that can be serialized and deserialized using pickle.

    A ``PicklableDict`` object can be created like a dictionary, for example:

    .. code-block:: python

        obj = PicklableDict(k1=3, k2=4)
        obj = PicklableDict({k1=3, k2=4})

    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self._is_picklable():
            raise TypeError(f'{self} is not picklable')


class PicklableWrapper(Picklable):
    r""" A wrapper of states that can be serialized and deserialized using pickle.

    :param obj: the object to wrap
    """

    def __init__(self, obj: Any) -> None:
        super().__init__()
        self._wrapped = obj

    @property
    def wrapped(self) -> Any:
        """
        :return: the wrapped object
        """
        return self._wrapped

    def __str__(self) -> str:
        return self._wrapped.__str__()


@local_checkpoint_saver(type=io.TextIOWrapper)
def save_file_to_local(obj: io.TextIOWrapper, path: str) -> None:
    with open(path, 'wb') as f:
        st_mode = os.fstat(obj.fileno()).st_mode
        dill.dump((obj, st_mode), f, fmode=dill.FILE_FMODE)


@local_checkpoint_loader(type=io.TextIOWrapper)
def load_file_from_local(path: str) -> io.TextIOWrapper:
    with open(path, 'rb') as f:
        (obj, st_mode) = dill.load(f)
        os.chmod(obj.name, st_mode)

    return obj


# TODO(p1): Think of some way to register primitive types
# programatically
@local_checkpoint_saver(type=bool)
def save_bool_to_local(obj: bool, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=bool)
def load_bool_from_local(path: str) -> bool:
    with open(path, 'rb') as f:
        obj = dill.load(f)

    return obj


@local_checkpoint_saver(type=int)
def save_int_to_local(obj: int, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=int)
def load_int_from_local(path: str) -> int:
    with open(path, 'rb') as f:
        obj = dill.load(f)

    return obj


@local_checkpoint_saver(type=float)
def save_float_to_local(obj: float, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=float)
def load_float_from_local(path: str) -> float:
    with open(path, 'rb') as f:
        obj = dill.load(f)

    return obj


@local_checkpoint_saver(type=str)
def save_str_to_local(obj: str, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=str)
def load_str_from_local(path: str) -> str:
    with open(path, 'rb') as f:
        obj = dill.load(f)

    return obj


@local_checkpoint_saver(type=tuple)
def save_tuple_to_local(obj: tuple, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=tuple)
def load_tuple_from_local(path: str) -> tuple:
    with open(path, 'rb') as f:
        obj = dill.load(f)

    return obj


@local_checkpoint_saver(type=list)
def save_list_to_local(obj: list, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=list)
def load_list_from_local(path: str) -> list:
    with open(path, 'rb') as f:
        obj = dill.load(f)

    return obj


@local_checkpoint_saver(type=Picklable)
def save_picklable_to_local(obj: Picklable, path: str) -> None:
    with open(path, 'wb') as f:
        dill.dump(obj, f)


@local_checkpoint_loader(type=Picklable)
def load_picklable_from_local(path: str) -> Picklable:
    with open(path, 'rb') as f:
        obj = dill.load(f)
    return obj


@local_checkpoint_deleter
def delete_local(path: str) -> None:
    Path(path).unlink()


@remote_checkpoint_saver(type=Picklable)
def send_to_checkpoint_service(obj: Picklable, socket: zmq.Socket, job_id: str, uid: str, key: str):
    with io.BytesIO() as buffer:
        dill.dump(obj, buffer)
        msg = CheckpointMessage(RequestType.SAVE, job_id=job_id, uid=uid, ckpt_name=key, body=buffer.getvalue())
        socket.send(msg.encode_message())
        socket.recv()


@remote_checkpoint_loader(type=Picklable)
def recv_checkpoint_from_service(socket: zmq.Socket, job_id: str, uid: str, key: str) -> Picklable:
    msg = CheckpointMessage(RequestType.LOAD, job_id=job_id, uid=uid, ckpt_name=key, body=b'')
    socket.send(msg.encode_message())
    response = socket.recv()
    ckpt_response = CheckpointMessage.parse_message(response)

    obj = dill.loads(ckpt_response.body)
    return obj


@remote_checkpoint_deleter
def delete_remote_checkpoint(socket: zmq.Socket, job_id: str, uid: str, key: str) -> None:
    msg = CheckpointMessage(RequestType.DEL, job_id=job_id, uid=uid, ckpt_name=key, body=b'')
    socket.send(msg.encode_message())
    socket.recv()


@s3_checkpoint_saver(type=Picklable)
def send_Picklable_checkpoint_to_s3(obj: Picklable, bucket_name: str, job_id: str, uid: str, key: str):
    with io.BytesIO() as buffer:
        dill.dump(obj, buffer)
        S3CheckpointHelper.save(bucket_name=bucket_name, job_id=job_id, uid=uid,
                                ckpt_name=key, checkpoint_data=buffer.getvalue())


@s3_checkpoint_loader(type=Picklable)
def recv_Picklable_checkpoint_from_s3(bucket_name: str, job_id: str, uid: str, key: str) -> Picklable:
    ckpt_response = S3CheckpointHelper.load(bucket_name=bucket_name, job_id=job_id, uid=uid, ckpt_name=key)

    obj = dill.loads(ckpt_response)
    return obj


@s3_checkpoint_deleter
def delete_s3_checkpoint(bucket_name: str, job_id: str, uid: str, key: str) -> None:
    S3CheckpointHelper.delete(bucket_name=bucket_name, job_id=job_id, uid=uid, ckpt_name=key)


@s3_checkpoint_saver(type=int)
def send_int_checkpoint_to_s3(obj: int, bucket_name: str, job_id: str, uid: str, key: str):
    with io.BytesIO() as buffer:
        dill.dump(obj, buffer)
        S3CheckpointHelper.save(bucket_name=bucket_name, job_id=job_id, uid=uid,
                                ckpt_name=key, checkpoint_data=buffer.getvalue())


@s3_checkpoint_loader(type=int)
def recv_int_checkpoint_from_s3(bucket_name: str, job_id: str, uid: str, key: str) -> int:
    ckpt_response = S3CheckpointHelper.load(bucket_name=bucket_name, job_id=job_id, uid=uid, ckpt_name=key)

    obj = dill.loads(ckpt_response)
    return obj
