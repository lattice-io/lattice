from lattice_addons.state import CHECKPOINT_TYPE, CHECKPOINT_CONFIG
from lattice_addons.state.ckpt_manager import CheckpointSetting
from lattice_autopatch_torch import patch, patch_module, patch_dataloader, patch_optimizer

import os
import tempfile
import pytest
import atexit
import multiprocessing as mp
from dataclasses import dataclass

from typing import Any, Callable, List

import numpy as np
import torch
import torch.utils.data as data
import torch.distributed as dist


class Polynomial(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.a = torch.nn.Parameter(torch.randn(()))
        self.b = torch.nn.Parameter(torch.randn(()))
        self.c = torch.nn.Parameter(torch.randn(()))
        self.d = torch.nn.Parameter(torch.randn(()))

    def forward(self, x):
        return self.a + self.b * x + self.c * x ** 2 + self.d * x ** 3


class PolynomialMultiplier(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.p1 = Polynomial()
        self.p2 = Polynomial()

    def forward(self, x):
        return self.p1(x) * self.p2(x)


class RandomDataset(data.Dataset):
    def __init__(self, size=10) -> None:
        super().__init__()
        self.size = size
        self.seq = np.random.randn(size)

    def __getitem__(self, index) -> int:
        return self.seq[index]

    def __len__(self) -> int:
        return self.size


class InfiniteDataLoader(data.DataLoader):
    """ Dataloader that reuses workers

    Uses same syntax as vanilla DataLoader
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cause of problem -- RepeatSampler is given a reference to the **unwrapped**
        # BatchSampler and iterator before __init__ is finished
        object.__setattr__(self, 'batch_sampler', RepeatSampler(self.batch_sampler))
        # Because our hook is run after __init__ we don't catch this
        self.iterator = super().__iter__()

    def __len__(self):
        return len(self.batch_sampler.sampler)

    def __iter__(self):
        for i in range(len(self)):
            yield next(self.iterator)


class RepeatSampler(object):
    """ Sampler that repeats forever

    Args:
        sampler (Sampler)
    """

    def __init__(self, sampler):
        self.sampler = sampler

    def __iter__(self):
        while True:
            yield from iter(self.sampler)


def patch_helper(target='all') -> None:
    targets = {
        'all': patch,
        'module': patch_module,
        'optimizer': patch_optimizer,
        'dataloader': patch_dataloader
    }
    target = targets.get(target, None)
    assert target is not None

    target('torch')

    root = tempfile.mkdtemp()
    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = f'root={root}'


# TODO(p0): Remove this
def exit_helper(fn: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        fn(*args, **kwargs)

        atexit._run_exitfuncs()
    return wrapper


@dataclass
class Value:
    type: str
    value: Any


def parse_args(args):
    inputs = []
    retval = []
    for arg in args:
        if isinstance(arg, Value):
            arg = mp.Value(arg.type, arg.value)
            retval.append(arg)
        inputs.append(arg)

    return (inputs, retval)


def parse_retval(retval):
    retval = [r.value for r in retval]
    return retval if len(retval) > 1 else retval[-1]


def launch(fn: Callable, *args) -> Any:
    inputs, retval = parse_args(args)

    fn = exit_helper(fn)

    p = mp.Process(target=fn, args=inputs)
    p.start()
    p.join()

    assert p.exitcode == 0
    if retval:
        return parse_retval(retval)


def dist_launch(n_proc: int, fn: Callable, *args) -> Any:
    procs = {}
    retvals = {}

    barrier = mp.Barrier(n_proc)
    for i in range(n_proc):
        inputs, retval = parse_args(args)

        @exit_helper
        def wrapper(b, *args, **kwargs):
            os.environ['MASTER_ADDR'] = 'localhost'
            os.environ['MASTER_PORT'] = '12355'
            os.environ['RANK'] = f'{i}'
            os.environ['WORLD_SIZE'] = f'{n_proc}'
            dist.init_process_group('gloo')

            fn(*args, **kwargs)

            b.wait()  # type: ignore[attr-defined]

        p = mp.Process(target=wrapper, args=[barrier] + inputs)
        p.start()

        procs[i] = p
        retvals[i] = retval

    for _, p in procs.items():
        p.join()
        assert p.exitcode == 0

    if retvals[0]:
        return parse_retval(retvals[0])  # Return the value of the first process


def test_module():
    def fn(retval: mp.Value, seed: int) -> None:
        torch.manual_seed(seed)

        mod = PolynomialMultiplier()
        retval.value = mod(1.0).item()  # type: ignore[attr-defined]

    # Without patch
    assert launch(fn, Value('f', 0), 1234) != pytest.approx(
        launch(fn, Value('f', 0), 4321),
        abs=1e-04)

    # With patch
    patch_helper('module')
    assert launch(fn, Value('f', 0), 1234) == pytest.approx(
        launch(fn, Value('f', 0), 4321),
        abs=1e-04)


def test_empty_module():
    def fn(retval: mp.Value, seed: int):
        torch.manual_seed(seed)
        mod0 = torch.nn.Sigmoid()
        # Variable use so flake8 doesn't complain
        mod0(torch.tensor([1.0]))

        mod1 = PolynomialMultiplier()
        retval.value = mod1(1.0).item()

    patch_helper('module')
    assert launch(fn, Value('f', 0), 1234) == pytest.approx(
        launch(fn, Value('f', 0), 4321),
        abs=1e-04
    )


def test_dist_module():
    def fn(retval: mp.Value, seed: int):
        torch.manual_seed(seed)

        model = PolynomialMultiplier()
        dist_model = torch.nn.parallel.DistributedDataParallel(model)

        retval.value = dist_model(1.0).item()  # type: ignore[attr-defined]

    # Without patch
    assert dist_launch(2, fn, Value('f', 0.), 1234) != dist_launch(2, fn, Value('f', 0.), 4321)

    # With patch
    patch_helper('module')
    assert dist_launch(2, fn, Value('f', 0.), 1234) == dist_launch(2, fn, Value('f', 0.), 4321)


def test_dist_sync_batch_norm_model():
    def fn(retval: mp.Value, seed: int):
        torch.manual_seed(seed)

        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.lnr = torch.nn.Linear(2, 3)
                self.bn = torch.nn.BatchNorm1d(3)

            def forward(self, x):
                out = self.lnr(x)
                out = self.bn(out)
                return out

        module = MyModule().to('cuda:0')
        module = torch.nn.SyncBatchNorm.convert_sync_batchnorm(module).to('cuda:0')
        dist_model = torch.nn.parallel.DistributedDataParallel(module).to('cuda:0')

        x = torch.randn(2, 2).to('cuda:0')
        dist_model(x)

        cfg = CheckpointSetting()
        ckpt_path = os.path.join(
            cfg.ckpt_config['root'],
            'LocalCheckpointCollectionManager:smg_000000',
            'SyncBatchNorm.0.TorchStateDict'
        )
        # Need to create some API to list existing checkpoints
        # TODO (p2): Penghzan
        # Expose API in `StateManagerGroup` to list checkpoints
        assert not os.path.exists(ckpt_path)

        retval.value = dist_model.state_dict()['module.bn.num_batches_tracked']

    # Return if no GPU available
    # TODO: Rework to use pytest.mark.skipif('not torch.cuda.is_available()')
    if not torch.cuda.is_available():
        return

    # Without patch
    # Number of tracked batches won't increment
    assert dist_launch(1, fn, Value('i', 0), 1234) == dist_launch(1, fn, Value('i', 0), 4321)

    # With patch
    patch_helper('module')
    # Number of tracked batches should increment
    assert dist_launch(1, fn, Value('i', 0), 1234) != dist_launch(1, fn, Value('i', 0), 4321)


def test_detecting_module_supersets():
    def fn(retval: mp.Value, seed: int):
        torch.manual_seed(seed)

        module = torch.nn.Sequential(
            # Linear and BatchNorm1d both have _nested_module_init_level == 0
            # but should NOT save their individual state because Sequential is
            # a parent module
            torch.nn.Linear(2, 3),
            torch.nn.BatchNorm1d(3)
        )

        # DDP module should be a superset of all previous state and therefore remove any managed
        # state that was a subset of it
        dist_model = torch.nn.parallel.DistributedDataParallel(module)

        x = torch.randn(2, 2)
        dist_model(x)

        retval.value = dist_model.state_dict()['module.1.num_batches_tracked']

        # Ensure that there is no checkpoint for Linear or BatchNorm1d
        submodule_names = ['Linear', 'BatchNorm1d']
        checkpoint_config = os.getenv('LATTICE_CHECKPOINT_CONFIG', None)
        if checkpoint_config:
            checkpoint_directory = checkpoint_config.split('=')[1]
            for mod_name in submodule_names:
                assert not os.path.exists(
                    os.path.join(
                        checkpoint_directory,
                        'LocalCheckpointCollectionManager:smg_000000',
                        f'{mod_name}.0.TorchStateDict'
                    )
                )

    # Without patch
    # Number of tracked batches won't increment
    assert dist_launch(1, fn, Value('i', 0), 1234) == dist_launch(1, fn, Value('i', 0), 4321)

    # With patch
    patch_helper('module')
    # Number of tracked batches should increment
    assert dist_launch(1, fn, Value('i', 0), 1234) != dist_launch(1, fn, Value('i', 0), 4321)


def test_dataloader():
    def fn(retval: mp.Value, data_size: int, batch_size: int, breakpoint: int):
        dataset = RandomDataset(data_size)
        loader = data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        left = 0
        for i, s in enumerate(loader):
            left += s.size(0)  # type: ignore[attr-defined]
            if i == breakpoint:
                break

        retval.value = left  # type: ignore[attr-defined]

    # Without patch
    assert launch(fn, Value('i', 0), 20, 2, 3) + \
        launch(fn, Value('i', 0), 20, 5, -1) != 20

    # With patch
    patch_helper('dataloader')
    assert launch(fn, Value('i', 0), 20, 2, 3) + \
        launch(fn, Value('i', 0), 20, 5, -1) == 20


def test_multiple_dataloaders():
    patch_helper('dataloader')

    train_data_size = 30
    test_data_size = 10
    train_data = RandomDataset(train_data_size)
    test_data = RandomDataset(test_data_size)

    train_loader = data.DataLoader(train_data, batch_size=3, shuffle=True)
    test_loader = data.DataLoader(test_data, batch_size=3, shuffle=True)

    num_sampled = 0
    for i, s in enumerate(train_loader):
        num_sampled += 1

    for i, s in enumerate(test_loader):
        num_sampled += 1

    assert train_data_size + test_data_size == 40


def test_single_epoch_dist_dataloader():
    def fn(retval: mp.Value, data_size: int, batch_size: int, breakpoint: int) -> None:
        dataset = RandomDataset(data_size)

        loader = data.DataLoader(
            dataset,
            sampler=data.DistributedSampler(dataset),
            batch_size=batch_size)

        left = 0
        for i, s in enumerate(loader):
            left += s.size(0)  # type: ignore[attr-defined]
            if i == breakpoint:
                break

        retval.value = left  # type: ignore[attr-defined]

    # Without patch
    assert dist_launch(2, fn, Value('i', 0), 30, 3, 3) * 2 + \
        dist_launch(3, fn, Value('i', 0), 30, 2, -1) * 3 != 30

    # With patch
    patch_helper('dataloader')
    assert dist_launch(2, fn, Value('i', 0), 30, 3, 3) * 2 + \
        dist_launch(3, fn, Value('i', 0), 30, 2, -1) * 3 == 30


def test_multiple_epoch_dist_dataloader():
    def fn(retval: mp.Value, data_size: int, batch_size: int,
           epochs: int, breakepoch: int, breakstep: int) -> None:
        dataset = RandomDataset(data_size)

        loader = data.DataLoader(
            dataset,
            sampler=data.DistributedSampler(dataset),
            batch_size=batch_size)

        left = 0
        for e in range(epochs):
            for i, s in enumerate(loader):
                left += s.size(0)
                if e == breakepoch and i == breakstep:
                    break

        retval.value = left  # type: ignore[attr-defined]

    # Without patch
    assert dist_launch(2, fn, Value('i', 0), 30, 3, 2, 1, 3) * 2 + \
        dist_launch(3, fn, Value('i', 0), 30, 2, 1, -1, -1) * 3 != 60

    # With patch
    patch_helper('dataloader')
    dist_launch(2, fn, Value('i', 0), 30, 3, 2, 1, 3) * 2 + \
        dist_launch(3, fn, Value('i', 0), 30, 2, 2, -1, -1) * 3 == 60


def test_custom_dataloader():
    def fn(retval: mp.Value, data_size: int, batch_size: int, breakpoint: int):
        dataset = RandomDataset(data_size)
        loader = InfiniteDataLoader(dataset, batch_size=batch_size, shuffle=True)

        left = 0
        for i, s in enumerate(loader):
            left += s.size(0)  # type: ignore[attr-defined]
            if i == breakpoint:
                break

        retval.value = left  # type: ignore[attr-defined]

    # Without patch
    assert launch(fn, Value('i', 0), 20, 2, 3) + \
        launch(fn, Value('i', 0), 20, 5, -1) != 20

    # With patch
    patch_helper('dataloader')
    assert launch(fn, Value('i', 0), 20, 2, 3) + \
        launch(fn, Value('i', 0), 20, 5, -1) == 20


# TODO(p0): Handle prefetching and fix this test case
@pytest.mark.skip(reason="Can not handle prefetching")
def test_multi_worker_dataloader():
    def fn(retval: mp.Value, data_size: int, batch_size: int, breakpoint: int):
        dataset = RandomDataset(data_size)
        loader = data.DataLoader(
            dataset,
            num_workers=1,
            batch_size=batch_size,
            shuffle=True)

        left = 0
        for i, s in enumerate(loader):
            left += s.size(0)  # type: ignore[attr-defined]
            if i == breakpoint:
                break

        retval.value = left  # type: ignore[attr-defined]

    # Without patch
    assert launch(fn, Value('i', 0), 20, 2, 3) + \
        launch(fn, Value('i', 0), 20, 5, -1) != 20

    # With patch
    patch_helper('dataloader')
    assert launch(fn, Value('i', 0), 20, 2, 3) + \
        launch(fn, Value('i', 0), 20, 5, -1) == 20


def test_optimizer():
    def fn(retval: mp.Value, inputs: List[torch.Tensor]) -> None:
        torch.manual_seed(1234)

        mod = PolynomialMultiplier()
        opt = torch.optim.Adam(params=mod.parameters())

        for i, inp in enumerate(inputs):
            opt.zero_grad()

            loss = mod(inp)
            loss.backward()
            opt.step()

            # Return the most recent loss value
            if i == len(inputs) - 1:
                retval.value = loss.item()  # type: ignore[attr-defined]

    inputs = [1, 2, 3]

    golden = launch(fn, Value('f', 0.), inputs)

    # Without patch
    _ = launch(fn, Value('f', 0.), inputs[:1])
    baseline = launch(fn, Value('f', 0.), inputs[1:])

    # With patch
    patch_helper('all')
    _ = launch(fn, Value('f', 0.), inputs[:1])
    patched = launch(fn, Value('f', 0.), inputs[1:])

    # The patched version should be closer to the golden
    assert abs(patched - golden) < abs(baseline - golden)


def test_added_param_group_optimizer():
    def fn(retval: mp.Value, inputs: List[torch.Tensor]) -> None:
        torch.manual_seed(1234)

        mod1 = PolynomialMultiplier()
        opt = torch.optim.Adam(mod1.parameters())

        mod2 = PolynomialMultiplier()
        opt.add_param_group({'params': mod2.parameters()})

        for i, inp in enumerate(inputs):
            opt.zero_grad()

            loss = mod2(inp)
            loss.backward()
            opt.step()

            # Return the most recent loss value
            if i == len(inputs) - 1:
                retval.value = loss.item()  # type: ignore[attr-defined]

    inputs = [1, 2, 3]

    golden = launch(fn, Value('f', 0.), inputs)

    # Without patch
    _ = launch(fn, Value('f', 0.), inputs[:1])
    baseline = launch(fn, Value('f', 0.), inputs[1:])

    # With patch
    patch_helper('all')
    _ = launch(fn, Value('f', 0.), inputs[:1])
    patched = launch(fn, Value('f', 0.), inputs[1:])

    # The patched version should be closer to the golden
    assert abs(patched - golden) < abs(baseline - golden)
