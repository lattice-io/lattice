from .constants import ADHOC_ATTRIBUTE_KEY, CONFIG_PERIODIC_SAVING
from .state import TorchStateDict
from lattice_addons.log import get_logger
from lattice_addons.state import StateManagerGroup, StateClosureManager
from wrapt import FunctionWrapper
from typing import Any, Callable

import torch

_logger = get_logger(__name__)
_nested_optimizer_level = 0


def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate


def build_preloading_wrapper(wrapped: Callable, loader: Callable) -> FunctionWrapper:
    @static_vars(loaded=False)
    def wrapper(wrapped, instance, args, kwargs):
        if wrapper.loaded is False:
            loader()  # type: ignore[arg-type]
            wrapper.loaded = True
        return wrapped(*args, **kwargs)

    return FunctionWrapper(wrapped, wrapper)


def build_post_step_wrapper(wrapped: Callable) -> FunctionWrapper:
    @static_vars(step=0)
    def wrapper(wrapped, instance, args, kwargs):
        mgr = StateManagerGroup()
        mgr.pause_periodic_saving()
        wrapped_output = wrapped(*args, **kwargs)
        mgr.resume_periodic_saving()
        return wrapped_output

    return FunctionWrapper(wrapped, wrapper)


def wrap_optimizer_init(__init__, self: torch.optim.Optimizer, args, kwargs) -> Any:
    global _nested_optimizer_level

    _nested_optimizer_level += 1
    retval = __init__(*args, **kwargs)
    _nested_optimizer_level -= 1

    if _nested_optimizer_level <= 0:
        _logger.debug(f'Invoke post init hook for {self.__class__.__name__}')

        mgr = StateManagerGroup()

        if mgr.ckpt_configs[CONFIG_PERIODIC_SAVING]:
            post_step_wrapper = build_post_step_wrapper(self.step)
            setattr(self, 'step', post_step_wrapper)

        key = mgr.keygen(self)
        mgr.register(key, StateClosureManager)

        state = mgr.get(key)
        if state is not None:
            # Delay state loading when optimizer is used, which is necessary if users use `Optimizer.add_param_group`
            wrapper = build_preloading_wrapper(
                self.step,
                lambda: self.load_state_dict(mgr.get(key)))  # type: ignore[arg-type]

            setattr(self, 'step', wrapper)

        mgr.update(key, lambda: TorchStateDict(**self.state_dict()))

        setattr(self, ADHOC_ATTRIBUTE_KEY, key)

    return retval
