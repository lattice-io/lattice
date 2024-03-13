import argparse
import random
import dill
import io
import zmq
import torch
import time
from enum import Enum
from dataclasses import dataclass
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


JOB_ID = 'test-job'
U_ID = 'uid'
NODE_ID = random.randint(0, 1000000)

# create a dummy model and optimizer
model = torch.nn.Linear(1, 1)
optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

mod_sd = model.state_dict()
opt_sd = optimizer.state_dict()


context = zmq.Context()
socket = context.socket(zmq.REQ)

parser = argparse.ArgumentParser()
parser.add_argument('--endpoint', type=str, default="lattice-checkpoint-svc")

args = parser.parse_args()


start_time = time.time()

socket.connect(f'tcp://{args.endpoint}:5555')

ping_msg = CheckpointMessage(RequestType.PING, JOB_ID, U_ID, '', b'')
socket.send(ping_msg.encode_message())
response = socket.recv()
response = CheckpointMessage.parse_message(response)
print(response)

# lock the checkpoint
lock_name = 'lock.model.pt'
node_info = {'node_id': NODE_ID}
print(f'Acquiring lock: {lock_name} for node: {node_info}')
lock_msg = CheckpointMessage(RequestType.ACQUIRE, JOB_ID, U_ID, lock_name, dill.dumps(node_info))
socket.send(lock_msg.encode_message())

response = socket.recv()
response = CheckpointMessage.parse_message(response)
response_node_info = dill.loads(response.body)
print("Lock response: ", response_node_info)

if (response_node_info['node_id'] == NODE_ID):
    with io.BytesIO() as cp_file:
        torch.save(mod_sd, cp_file)
        cp_file.seek(0)
        print('Creating model checkpoint message')
        save_msg1 = CheckpointMessage(RequestType.SAVE, JOB_ID, U_ID, 'model.pt', cp_file.getvalue())
        print('Sending model checkpoint message')
        socket.send(save_msg1.encode_message())
        response = socket.recv()
        response = CheckpointMessage.parse_message(response)
        print(response.body)

    # release the lock
    print(f'Releasing lock: {lock_name} for node: {node_info}')
    release_msg = CheckpointMessage(RequestType.RELEASE, JOB_ID, U_ID, lock_name, b'')
    socket.send(release_msg.encode_message())

    response = socket.recv()
    response = CheckpointMessage.parse_message(response)
    print(response.body)

# lock the checkpoint
lock_name = 'lock.opt.pt'
node_info = {'node_id': NODE_ID}
print(f'Acquiring lock: {lock_name} for node: {node_info}')
lock_msg = CheckpointMessage(RequestType.ACQUIRE, JOB_ID, U_ID, lock_name, dill.dumps(node_info))
socket.send(lock_msg.encode_message())

response = socket.recv()
response = CheckpointMessage.parse_message(response)
response_node_info = dill.loads(response.body)
print("Lock response: ", response_node_info)

if (response_node_info['node_id'] == NODE_ID):
    with io.BytesIO() as cp_file:
        torch.save(opt_sd, cp_file)
        cp_file.seek(0)
        print('Creating optimizer checkpoint message')
        save_msg2 = CheckpointMessage(RequestType.SAVE, JOB_ID, U_ID, 'opt.pt', cp_file.getvalue())
        print('Sending optimizer checkpoint message')
        socket.send(save_msg2.encode_message())
        response = socket.recv()
        response = CheckpointMessage.parse_message(response)
        print(response.body)

    # release the lock
    print(f'Releasing lock: {lock_name} for node: {node_info}')
    release_msg = CheckpointMessage(RequestType.RELEASE, JOB_ID, U_ID, lock_name, b'')
    socket.send(release_msg.encode_message())

    response = socket.recv()
    response = CheckpointMessage.parse_message(response)
    print(response.body)

print('Getting list of all checkpoints')
list_msg = CheckpointMessage(RequestType.LIST, JOB_ID, U_ID, '', b'')
socket.send(list_msg.encode_message())

list_response = socket.recv()
ckpt_response = CheckpointMessage.parse_message(list_response)
print('LIST', ckpt_response.body)

ckpt_name = 'model.pt'

print('Retrievining a checkpoint')
load_msg = CheckpointMessage(RequestType.LOAD, JOB_ID, U_ID, ckpt_name, b'')
socket.send(load_msg.encode_message())

load_response = socket.recv()
ckpt_response = CheckpointMessage.parse_message(load_response)
if(ckpt_response.req_type == RequestType.LOAD):
    model.load_state_dict(torch.load(io.BytesIO(ckpt_response.body)))
    print('Loaded model: ', model)
else:
    print('Error loading model: ', ckpt_response.body)

print(f'Deleting checkpoint "{ckpt_name}"')
del_msg = CheckpointMessage(RequestType.DEL, JOB_ID, U_ID, ckpt_name, b'')
socket.send(del_msg.encode_message())

del_response = socket.recv()
ckpt_response = CheckpointMessage.parse_message(del_response)
print('DEL', ckpt_response.body)

print('Getting list of all checkpoints')
list_msg = CheckpointMessage(RequestType.LIST, JOB_ID, U_ID, '', b'')
socket.send(list_msg.encode_message())

list_response = socket.recv()
ckpt_response = CheckpointMessage.parse_message(list_response)
print('LIST', ckpt_response.body)

print("Client run completed successfully.\n")

end_time = time.time()
print("Total time taken: ", end_time - start_time)
