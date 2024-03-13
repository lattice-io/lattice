import os

import torch
import torch.distributed as dist

local_rank = os.environ['LOCAL_RANK']
rank = os.environ['RANK']
world_size = os.environ['WORLD_SIZE']
master_addr = os.environ['MASTER_ADDR']
master_port = os.environ['MASTER_PORT']

print('Distributed Config:')
print('\tLOCAL_RANK:', local_rank)
print('\tRANK:', rank)
print('\tWORLD_SIZE:', world_size)
print('\tMASTER_ADDR:', master_addr)
print('\tMASTER_PORT:', master_port)

dist.init_process_group(backend='gloo')

x = torch.tensor([dist.get_rank()])

dist.all_reduce(x, op=dist.ReduceOp.SUM)

print('Final tensor:', x)
