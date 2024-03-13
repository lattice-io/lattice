import dill

from dataclasses import dataclass
from enum import Enum
from typing import Any



class RequestType(Enum):
    PING = 0
    LIST = 1
    SAVE = 2
    LOAD = 3
    DEL = 4
    ACQUIRE = 5
    RELEASE = 6
    ERROR = 101


class RecvTimedOutException(Exception):
    def __init__(self):
        pass


@dataclass
class CheckpointResponse:
    req_type: RequestType
    job_id: str
    uid: str
    ckpt_name: str
    body: Any


class CheckpointMessage():
    def __init__(self, req_type: RequestType, job_id: str, uid: str, ckpt_name: str, body: bytes):
        self._req_type = req_type
        self._job_id = job_id
        self._uid = uid
        self._ckpt_name = ckpt_name
        self._body = body


    def encode_message(self):
        bytes_to_send = {
            'type': self._req_type.value,
            'job_id': self._job_id,
            'uid': self._uid,
            'ckpt_name': self._ckpt_name,
            'body': self._body
        }

        return dill.dumps(bytes_to_send)


    @staticmethod
    def parse_message(message):
        decoded_message = dill.loads(message)

        return CheckpointResponse(RequestType(decoded_message['type']), decoded_message['job_id'],
                                  decoded_message['uid'], decoded_message['ckpt_name'], decoded_message['body'])
