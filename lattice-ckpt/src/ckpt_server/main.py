import argparse
import os
import sys
import time
import zmq
import threading
from collections import defaultdict
from pathlib import Path
from typing import Dict

sys.path.append('./')

from utils.utils import (
    RequestType,
    RecvTimedOutException,
    CheckpointMessage,
)


TOTAL_BYTES_THRESHHOLD = (1024 ** 3) * 4 # 4 GiB toal
SINGLE_CKPT_BYTES_THRESHHOLD = (1024 ** 3) * 1 # 1 GiB per ckpt
ACK = b'ACK'


parser = argparse.ArgumentParser()
parser.add_argument('--root-dir', type=str, required=True, help="Path to directory where checkpoints should be stored")
parser.add_argument('--num-threads', type=int, default=4, help="Number of threads to use")


class CheckpointService:
    def __init__(self, root_dir, num_threads, context=None):
        self.context = context or zmq.Context.instance()
        self.url_worker = "inproc://workers"
        self.url_client = "tcp://*:5555"
        
        # Socket to talk to clients
        self.clients = self.context.socket(zmq.ROUTER)
        self.clients.bind(self.url_client)
        
        # Socket to talk to workers
        self.workers = self.context.socket(zmq.DEALER)
        self.workers.bind(self.url_worker)
        
        self.num_threads = num_threads
        self._lock = threading.Lock()

        self.checkpoint_cache: Dict[Dict[str, bytes]] = defaultdict(lambda: defaultdict(dict))
        self._root_dir = Path(root_dir)

    def cleanup(self):
        self.clients.close()
        self.workers.close()
        self.context.term()


    def _timed_recv(self, timeout: int = 5) -> bytes:
        start = time.time()
        while time.time() - start < timeout:
            try:
                return self.socket.recv(zmq.NOBLOCK)
            except zmq.error.Again:
                time.sleep(0.1)

        raise RecvTimedOutException()


    def _handle_ping_request(self, socket, job_id: str) -> None:
        msg = CheckpointMessage(RequestType.PING, job_id=job_id, uid='', ckpt_name='', body=ACK)
        socket.send(msg.encode_message())


    def _handle_list_request(self, socket, job_id: str) -> None:
        all_checkpoints = {}
        for k, v in self.checkpoint_cache[job_id].items():
            all_checkpoints[k] = list(v.keys())

        msg = CheckpointMessage(RequestType.LIST, job_id=job_id, uid='', ckpt_name='', body=all_checkpoints)
        socket.send(msg.encode_message())


    def _handle_save_request(self, socket, job_id: str, uid: str, ckpt_name: str, checkpoint_data: bytes) -> None:
        # TODO: If we need to save space, write some checkpoints to disk
        self.checkpoint_cache[job_id][uid][ckpt_name] = checkpoint_data

        msg = CheckpointMessage(RequestType.SAVE, job_id, uid, ckpt_name, ACK)
        socket.send(msg.encode_message())


    def _handle_load_request(self, socket, job_id: str, uid: str, ckpt_name: str) -> None:
        try:
            checkpoint_data = self.checkpoint_cache[job_id][uid][ckpt_name]
            response_msg = CheckpointMessage(RequestType.LOAD, job_id, uid, ckpt_name, checkpoint_data)
            socket.send(response_msg.encode_message())
        except KeyError:
            error_response = CheckpointMessage(RequestType.ERROR, job_id, uid, ckpt_name, b'Checkpoint not found')
            socket.send(error_response.encode_message())


    def _handle_del_request(self, socket, job_id: str, uid: str, ckpt_name: str) -> None:
        try:
            del self.checkpoint_cache[job_id][uid][ckpt_name]
            msg = CheckpointMessage(RequestType.DEL, job_id, uid, ckpt_name, ACK)
            socket.send(msg.encode_message())
        except KeyError:
            error_response = CheckpointMessage(RequestType.ERROR, job_id, uid, ckpt_name, b'Checkpoint not found')
            socket.send(error_response.encode_message())


    def _handle_acquire_request(self, socket, job_id: str, uid: str, lock_name: str, node_info: Dict) -> None:
        with self._lock:
            try:
                lock = self.checkpoint_cache[job_id][uid][lock_name]
                msg = CheckpointMessage(RequestType.ACQUIRE, job_id, uid, lock_name, lock)
                socket.send(msg.encode_message())
            except KeyError:
                self.checkpoint_cache[job_id][uid][lock_name] = node_info
                msg = CheckpointMessage(RequestType.ACQUIRE, job_id, uid, lock_name, node_info)
                socket.send(msg.encode_message())


    def _handle_release_request(self, socket, job_id: str, uid: str, lock_name: str) -> None:
        try:
            del self.checkpoint_cache[job_id][uid][lock_name]
            msg = CheckpointMessage(RequestType.RELEASE, job_id, uid, lock_name, ACK)
            socket.send(msg.encode_message())
        except KeyError:
            error_response = CheckpointMessage(RequestType.ERROR, job_id, uid, lock_name, b'Lock not found')
            socket.send(error_response.encode_message())


    def worker_routine(self, worker_id: int) -> None:
        # Socket to talk to dispatcher
        socket = self.context.socket(zmq.REP)
        socket.connect(self.url_worker)

        while True:
            print(f'Worker {worker_id} waiting for message...')

            message = socket.recv()

            parsed_msg = CheckpointMessage.parse_message(message)

            if parsed_msg.req_type == RequestType.PING:
                self._handle_ping_request(socket, parsed_msg.job_id)
            elif parsed_msg.req_type == RequestType.LIST:
                self._handle_list_request(socket, parsed_msg.job_id)
            elif parsed_msg.req_type == RequestType.SAVE:
                self._handle_save_request(socket, parsed_msg.job_id, parsed_msg.uid,
                                          parsed_msg.ckpt_name, parsed_msg.body)
            elif parsed_msg.req_type == RequestType.LOAD:
                self._handle_load_request(socket, parsed_msg.job_id, parsed_msg.uid,
                                          parsed_msg.ckpt_name)
            elif parsed_msg.req_type == RequestType.DEL:
                self._handle_del_request(socket, parsed_msg.job_id, parsed_msg.uid, 
                                         parsed_msg.ckpt_name)
            elif parsed_msg.req_type == RequestType.ACQUIRE:
                self._handle_acquire_request(socket, parsed_msg.job_id, parsed_msg.uid,
                                             parsed_msg.ckpt_name, parsed_msg.body)
            elif parsed_msg.req_type == RequestType.RELEASE:
                self._handle_release_request(socket, parsed_msg.job_id, parsed_msg.uid,
                                             parsed_msg.ckpt_name)
            else:
                raise ValueError(f'Invalid request type {parsed_msg.req_type}')

            print(f'Worker {worker_id} finished handling message')

    def launch(self) -> None:
        # Launch pool of worker threads
        for thread_id in range(self.num_threads):
            thread = threading.Thread(target=self.worker_routine, args=(thread_id,))
            thread.daemon = True
            thread.start()

        zmq.proxy(self.clients, self.workers)

def main():
    args = parser.parse_args()

    manager = CheckpointService(args.root_dir, args.num_threads)
    manager.launch()

if __name__ == '__main__':
    main()
