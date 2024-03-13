from lattice_addons.state import (
    local_checkpoint_saver, local_checkpoint_loader,
    remote_checkpoint_saver, remote_checkpoint_loader,
    s3_checkpoint_saver, s3_checkpoint_loader,
)
from lattice_addons.state import State
from lattice_addons.state.distributed.utils import (
    RequestType,
    CheckpointMessage,
)
from collections import OrderedDict
from lattice_addons.state import S3CheckpointHelper

import io
import torch
import zmq


class TorchStateDict(OrderedDict, State):
    ...


@local_checkpoint_saver(type=TorchStateDict)
def save_tsd_to_local(obj: TorchStateDict, path: str) -> None:
    torch.save(obj, path)


@local_checkpoint_loader(type=TorchStateDict)
def load_tsd_from_local(path: str) -> TorchStateDict:
    return torch.load(path)


@remote_checkpoint_saver(type=TorchStateDict)
def save_tsd_to_remote(obj: TorchStateDict, socket: zmq.Socket, job_id: str, uid: str, key: str):
    with io.BytesIO() as buffer:
        torch.save(obj, buffer)
        buffer.seek(0)
        msg = CheckpointMessage(RequestType.SAVE, job_id=job_id, uid=uid, ckpt_name=key, body=buffer.getvalue())
        socket.send(msg.encode_message())
        socket.recv()


@remote_checkpoint_loader(type=TorchStateDict)
def load_tsd_from_remote(socket: zmq.Socket, job_id: str, uid: str, key: str) -> TorchStateDict:
    msg = CheckpointMessage(RequestType.LOAD, job_id=job_id, uid=uid, ckpt_name=key, body=b'')
    socket.send(msg.encode_message())
    response = socket.recv()
    ckpt_response = CheckpointMessage.parse_message(response)

    with io.BytesIO(ckpt_response.body) as buffer:
        buffer.seek(0)
        sd = torch.load(buffer)

    return TorchStateDict(sd)


@s3_checkpoint_saver(type=TorchStateDict)
def save_tsd_to_s3(obj: TorchStateDict, bucket_name: str, job_id: str, uid: str, key: str):
    with io.BytesIO() as buffer:
        torch.save(obj, buffer)
        buffer.seek(0)
        S3CheckpointHelper.save(bucket_name=bucket_name, job_id=job_id, uid=uid,
                                ckpt_name=key, checkpoint_data=buffer.getvalue())


@s3_checkpoint_loader(type=TorchStateDict)
def load_tsd_from_s3(bucket_name: str, job_id: str, uid: str, key: str) -> TorchStateDict:
    ckpt_response = S3CheckpointHelper.load(bucket_name=bucket_name, job_id=job_id, uid=uid, ckpt_name=key)

    with io.BytesIO(ckpt_response) as buffer:
        buffer.seek(0)
        sd = torch.load(buffer)

    return TorchStateDict(sd)
