from .constants import ADHOC_ATTRIBUTE_KEY
from lattice_addons.log import get_logger
from lattice_addons.state import StateManagerGroup, StateClosureManager, PicklableWrapper
from lattice_addons.patch import UniversalWrapper

from dataclasses import dataclass
from typing import Callable, TypeVar, Iterator, Iterable, List, Any

import torch.utils.data as data

from wrapt import FunctionWrapper

_logger = get_logger(__name__)
_nested_dataloader_level = 0


T_co = TypeVar('T_co', covariant=True)


# TODO(p0): Create a base class for these wrappers. There is redundant code here,
# such as the static_vars being implemented in both data.py and optimizer.py
# Jira Link: https://breezeml.atlassian.net/browse/RD-426

def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate


@dataclass
class IterRecord:
    num_yielded: int
    length: int


class IteratorWrapper(UniversalWrapper):
    def __init__(self, iterator: Iterator[T_co], record: IterRecord) -> None:
        super().__init__(iterator)

        # Unfinished iterator or completed iterator
        if record.num_yielded != 0:
            try:
                for _ in range(record.num_yielded):
                    _ = next(self._base)
            except StopIteration:
                pass

        self._record = record

    def __next__(self) -> Any:
        # TODO(p0): When exit a training loop, you can have a sample that is fetched but not used to update the
        # weights, which will lead to a worry record.

        if self._record.num_yielded == self._record.length:
            raise StopIteration()

        retval = next(self._base)
        self._record.num_yielded += 1
        return retval

    def __iter__(self) -> Iterator[T_co]:
        return self


class SamplerWrapper(UniversalWrapper):
    def __init__(self, sampler: Iterable[Any], iter_records: List[IterRecord]) -> None:
        super().__init__(sampler)
        self._iter_records = iter_records
        self._iter_count = 0

        for i, record in enumerate(self._iter_records):
            if record.length == len(self._base) and record.length == record.num_yielded:
                continue

            # Map the iterator progress to the number of yielded if record length
            # changes, which can happen in the distributed sampler if the batch size changed
            if record.length != len(self._base):
                progress = record.num_yielded / record.length
                record.num_yielded = int(len(self._base) * progress)
                record.length = len(self._base)
                self._iter_records[i] = record

    def __getattr__(self, attr) -> Any:
        if attr == 'iter_records':
            return self._iter_records
        return super().__getattr__(attr)

    def __iter__(self) -> Iterator[T_co]:
        # Create a new record for this iterator if there is no existing record
        if self._iter_count == len(self._iter_records):
            self._iter_records.append(IterRecord(0, len(self._base)))

        record = self._iter_records[self._iter_count]

        retval = iter(self._base)
        self._iter_count += 1

        return IteratorWrapper(retval, record)

    def __len__(self) -> int:
        if self._iter_count == len(self._iter_records):
            return len(self._base)
        else:
            assert self._iter_count < len(self._iter_records)
            return len(self._base) - self._iter_records[self._iter_count].num_yielded


@static_vars(is_wrapped=False)
def build_pre_itr_wrapper(wrapped: Callable) -> FunctionWrapper:
    def wrapper(wrapped, instance, args, kwargs):
        wrapped_output = wrapped(*args, **kwargs)
        mgr = StateManagerGroup()
        mgr.pause_periodic_saving()
        return wrapped_output
    if build_pre_itr_wrapper.is_wrapped:
        return wrapped
    else:
        build_pre_itr_wrapper.is_wrapped = True
        return FunctionWrapper(wrapped, wrapper)


def wrap_dataloader_init(__init__, self: data.DataLoader, args, kwargs) -> Any:
    global _nested_dataloader_level

    _nested_dataloader_level += 1
    retval = __init__(*args, **kwargs)
    _nested_dataloader_level -= 1

    if _nested_dataloader_level <= 0:
        _logger.debug(f'Invoke post init hook for {self.__class__.__name__}')

        # Bypass __setattr__ protection
        self._DataLoader__initialized = False

        mgr = StateManagerGroup()

        # TODO: We need to figure out how to handle the the deadlock issue when
        # when we have several data loaders. For now, the locking is moved to the
        # optimizer step function

        # if mgr.ckpt_configs[CONFIG_PERIODIC_SAVING]:
        #     DataLoaderIterClass = type(self.__iter__())
        #     wrapper = build_pre_itr_wrapper(DataLoaderIterClass.__next__)
        #     setattr(DataLoaderIterClass, '__next__', wrapper)

        key = mgr.keygen(self)

        mgr.register(key, StateClosureManager)

        state = mgr.get(key)
        if state is not None:
            assert isinstance(state, PicklableWrapper)
            wrapper = SamplerWrapper(self.sampler, state.wrapped)
        else:
            wrapper = SamplerWrapper(self.sampler, [])
        mgr.update(key, lambda: PicklableWrapper(wrapper.iter_records))

        self.sampler = wrapper  # type: ignore[assignment]
        if self._auto_collation:
            self.batch_sampler = data.BatchSampler(
                wrapper, self.batch_size, self.drop_last)  # type: ignore[arg-type]

        setattr(self, ADHOC_ATTRIBUTE_KEY, key)
        self._DataLoader__initialized = True

    return retval
