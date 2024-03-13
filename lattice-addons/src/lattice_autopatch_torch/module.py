from .constants import ADHOC_ATTRIBUTE_KEY
from .state import TorchStateDict
from lattice_addons.log import get_logger
from lattice_addons.state import StateManagerGroup, StateClosureManager

from typing import Any, Dict, Callable

import torch


_logger = get_logger(__name__)

# List of blacklisted module types
blacklist = ['SyncBatchNorm']


# Hook guardians
_nested_module_init_level: int = 0
_cached_state_closures: Dict[str, Callable] = {}
_keys_to_delete = set()


def _check_blacklisted_models(name: str) -> bool:
    return name in blacklist


def is_subset(set1, set2) -> bool:
    matched = 0
    try:
        for v1 in set1:
            for v2 in set2:
                if v1.size() == v2.size() and torch.all(torch.eq(v1, v2)):
                    matched += 1
                    break
    except RuntimeError:
        return False

    # All elements in set1 had a match in set2
    return matched == len(set1)


def _is_exact_match(set1, set2) -> bool:
    for p1, p2 in zip(set1, set2):
        try:
            if p1.size() != p2.size() or not torch.all(torch.eq(p2, p2)):
                return False
        # Likely raised by state residing on different devices
        except RuntimeError:
            return False

    return True


def _compare_states(key_name: str, closure, state: TorchStateDict) -> bool:
    r""" Determine whether there is unique state within this state dict
    """
    global _keys_to_delete
    closure_values = closure().values()
    state_values = state.values()

    # New state may already exist in the _cached_state_closures
    if len(closure_values) > len(state_values):
        if is_subset(state_values, closure_values):
            return True

    # New state may be a superset of the existinging closures
    # in which case they are no longer necessary
    elif len(closure_values) < len(state_values):
        if is_subset(closure_values, state_values):
            _keys_to_delete.add(key_name)
            return False

    # May be the exact same state (for example when using DDP)
    # If they are a match, keep the newest state
    else:
        exact_match = _is_exact_match(state_values, closure_values)
        if exact_match:
            _keys_to_delete.add(key_name)

        return False

    return False


def wrap_module_init(__init__, self: torch.nn.Module, args, kwargs) -> Any:
    # TODO(p1): Make this thread safe. ~ Same for data and optimizer.
    # TODO(p0): Create a common wrapper builder, as this implementation is hard to understand and manage
    # ~ Same for data and optimizer.
    # TODO(p0): Directly wrap "__init__" sometimes can trigger wired internal errors. For example, when you wrapt
    # the initializer for pathlib.Path. ~ Same for data and optimizer.

    global _nested_module_init_level
    global _cached_state_closures
    global _keys_to_delete

    _nested_module_init_level += 1
    retval = __init__(*args, **kwargs)
    _nested_module_init_level -= 1

    def _post_init_hook_predicates() -> bool:
        # Only execute hook for root modules.
        if _nested_module_init_level > 0:
            return False

        # Only execute hook for the modules with states. Can be used to skip
        # stateless computations like torchvision.transforms.
        state = self.state_dict()
        if state is None:
            return False

        if _check_blacklisted_models(self.__class__.__name__):
            return False

        # Only execute hook for the modules with unique states. Can be used to
        # skip wrapper upon normal modules like DistributedDataParallel.
        state = TorchStateDict(**state)

        # TODO (p1): Find a more optimized way than just brute force
        for key_name, closure in _cached_state_closures.items():
            subset_of = _compare_states(key_name, closure, state)
            if subset_of:
                _keys_to_delete.clear()
                return False

        return True

    if _post_init_hook_predicates():
        _logger.debug(f'Invoke post init hook for {self.__class__.__name__}')

        mgr = StateManagerGroup()
        key = mgr.keygen(self)

        # NOTE: Use a closure with the strong reference to this module for
        # the state manager. In this case, you don't need to explicitly invoke
        # update(). But state manager will increase the reference counting for
        # the module, which may result in additional memory consumption.
        mgr.register(key, StateClosureManager)

        # Auto-load state if there is any existing checkpoint
        state = mgr.get(key)
        if state is not None:
            self.load_state_dict(state)  # type: ignore[arg-type]

        def getter() -> TorchStateDict:
            return TorchStateDict(**self.state_dict())

        mgr.update(key, getter)
        _cached_state_closures[key] = getter

        for dead_key in _keys_to_delete:
            if dead_key in _cached_state_closures:
                del _cached_state_closures[dead_key]

            if mgr.contain(dead_key):
                mgr.delete(dead_key)
        _keys_to_delete.clear()

        # Record key as an ad-hoc attribute, as we may need to use it for
        # saving states
        setattr(self, ADHOC_ATTRIBUTE_KEY, key)

    return retval
