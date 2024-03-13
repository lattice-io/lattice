from .ckpt_manager import (
    BaseCheckpointManager, BaseCheckpointCollectionManager,
    CheckpointSetting, CheckpointCollectionSetting
)
from .constants import (
    CONFIG_ATEXIT_SAVING, CONFIG_PERIODIC_SAVING, CONFIG_PERIODIC_SAVING_INTERVAL
)
from .util import _UIDSingletonABC, _Singleton
from ..log import get_logger

import abc
import ast
import copy
import weakref
import sys
import atexit
import signal
import inspect
import threading
import time
from collections import defaultdict
from typing import Any, Optional, Type, Dict, DefaultDict, Callable, List

logger = get_logger(__name__)


# States
# ------

class State():
    r""" The base class of all types of state.

    This class does not contain any property or method. All state classes should be defined by inheriting this class,
    before used as inputs to any state manager APIs.
    """
    ...


# State managers
# --------------

class BaseStateManager(metaclass=_UIDSingletonABC):
    r""" An abstract base class for state managers.

    State managers with specific types and UIDs are singletons. Once a state manager is created, the manager will
    always exist until the current process terminates. All the succeeding creation of a state manager
    will bring up the cached one.

    :param uid: The UID for the state manager
    """

    def __init__(self, uid: str) -> None:
        self._uid = uid
        self._state: Optional[Any] = None

        self._ckpt_mgr: BaseCheckpointManager
        self._register_ckpt()

    def _register_ckpt(self) -> None:
        settings = CheckpointSetting()
        ckpt_mgr_type = settings.ckpt_type
        ckpt_mgr_config = settings.ckpt_config
        self._ckpt_mgr = ckpt_mgr_type(self._uid, **ckpt_mgr_config)

    @abc.abstractmethod
    def _update_impl(self, state: State):
        pass

    @abc.abstractmethod
    def _get_impl(self) -> Any:
        pass

    @abc.abstractmethod
    def _delete_impl(self) -> Any:
        pass

    def update(self, state: Any) -> None:
        r"""
        :param state: The updated state
        """

        if state is None:
            return
        return self._update_impl(state)

    def get(self) -> Optional[State]:
        r"""
        :return: The managed state, or `None` if no updated state
        """

        if self._state is None:
            return None
        return self._get_impl()

    def delete(self) -> None:
        self._delete_impl()

    def save(self) -> None:
        r""" Save the managed state using the configured checkpoint manager. """

        if self._state is None:
            logger.debug(f'Can not find valid state in {self} for saving')
            return

        self._ckpt_mgr.save(self.get())  # type: ignore[union-attr]

    def load(self) -> None:
        r""" Use the configured checkpoint manager to load a state from an existing checkpoint."""

        state = self._ckpt_mgr.load()  # type: ignore[union-attr]

        if state is not None:
            self._load_impl(state)

    @abc.abstractmethod
    def _load_impl(self, state: Any) -> None:
        pass

    def __str__(self) -> str:
        return f'{self.__class__.__name__}:{self._uid}'


class StateManager(BaseStateManager):
    r""" Maintain a reference of the state. """

    def _update_impl(self, state: State):
        self._state = state

    def _get_impl(self) -> Any:
        return self._state

    def _delete_impl(self) -> Any:
        self._state = None

    def _load_impl(self, state: Any) -> None:
        self._state = state


class StateSymbolicManager(BaseStateManager):
    r""" Track a value by its symbolic state (variable name)"""
    def __init__(self, uid: str):
        super().__init__(uid)
        self._alloc_site_func_name: Optional[str] = None
        self._var_name: Optional[str] = None
        self._loaded_value = None

    def _get_var_name(self) -> Optional[str]:
        fr: inspect.FrameInfo = inspect.stack()[3]
        frame_code = fr.code_context
        if frame_code:
            update_call_source = frame_code[0].strip()
        else:
            return None

        tree = ast.parse(update_call_source)
        # Can assume body len is 1 since we only parse one line of code
        expr = tree.body[0]
        assert isinstance(expr, ast.Expr)
        value = expr.value
        assert isinstance(value, ast.Call)

        # Given we know the call structure from here, we know that the
        # arg passed to this function is the name of the variable we
        # want to track
        arg_id = value.args[0]
        assert isinstance(arg_id, ast.Name)
        var_name = arg_id.id

        return var_name

    def _get_caller_func_name(self) -> str:
        fr = inspect.stack()[3]
        return fr.function

    def _update_impl(self, state: State):
        self._alloc_site_func_name = self._get_caller_func_name()
        self._var_name = self._get_var_name()
        self._state = state

        # If we had loaded some value from checkpoint it is now
        # obsolete
        self._loaded_value = None

    def _get_impl(self) -> Any:
        # No state was loaded and not state has been tracked
        if self._loaded_value is None and self._var_name is None and self._alloc_site_func_name is None:
            return None

        # Return state that was loaded from checkpoint
        if self._loaded_value is not None:
            value = self._loaded_value
            self._loaded_value = None
            return value

        for frame in inspect.stack():
            if frame.function == self._alloc_site_func_name:
                break

        if self._var_name is not None:
            self._state = frame.frame.f_locals[self._var_name]
            return self._state
        else:
            return self._state

    def _delete_impl(self) -> Any:
        self._alloc_site_func_name = None
        self._var_name = None
        self._loaded_value = None
        self._state = None

    def _load_impl(self, state: Any) -> None:
        self._loaded_value = state


class StateCopyManager(BaseStateManager):
    r""" Maintain a copy of the state. """

    # TODO(p0): Implement a periodical and async saver

    def _update_impl(self, state: State):
        self._state = copy.deepcopy(state)

    def _get_impl(self) -> Any:
        return copy.deepcopy(self._state)

    def _delete_impl(self) -> Any:
        self._state = None

    def _load_impl(self, state: Any) -> None:
        self._state = state


class StateRefManager(BaseStateManager):
    r""" Maintain a weak reference of the state. """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tmp_owned_state: Optional[State] = None
        self._state: Optional[weakref.ReferenceType]

    def _update_impl(self, state: State):
        self._state = weakref.ref(state)

    # TODO(p2): When there is an immediate save() after load() without get():
    # ```
    #   mgr.load()
    #   mgr.save() <---
    #   mgr.get() ---> None
    # ````
    # The last save() will invoke get to get a transient object for saving.
    # It will consume state so that leave a None state in the state mgr. This
    # can also happen in StateManagerGroup.save.
    # One solution is to distinguish whether the get is invoked externally or
    # internally, and if it is invoked internally, we still need to keep the
    # `_tmp_owned_state`.
    def _get_impl(self) -> Any:
        assert self._state is not None
        retval = self._state()

        if self._tmp_owned_state is retval:
            self._tmp_owned_state = None
        return retval

    def _load_impl(self, state: Any) -> None:
        self._tmp_owned_state = state
        self.update(state)

    def _delete_impl(self) -> Any:
        # Automatically delete when the state is garbage collected
        pass


class StateClosureManager(BaseStateManager):
    r""" Maintain a closure to get the state. """

    def update(self, closure: Callable[[], State]) -> None:
        r""" Update the closure to get the managed state. """
        self._state = closure

    def _update_impl(self, state: State):
        pass

    def _load_impl(self, state: Any) -> None:
        def closure() -> Any:
            return state
        self.update(closure)

    def _get_impl(self) -> Any:
        assert self._state is not None
        return self._state()

    def _delete_impl(self) -> Any:
        self._state = None


# State manager groups
# --------------------

StateManagerGroupCheckpointUID = 'smg'


class StateManagerGroup(metaclass=_Singleton):
    r""" A group of active state managers.

    The state manager group is a singleton.
    """

    def __init__(self) -> None:
        logger.debug('Initialize state manager group')

        self._states: Dict[str, BaseStateManager]
        self._key_history: DefaultDict[str, int]
        self._reset()

        self._ckpt_mgr: BaseCheckpointCollectionManager
        self._register_ckpt()
        self.ckpt_configs = self._ckpt_mgr.get_configs()

        self._register_cleanup()

        self._lock = threading.Lock()
        self._priodic_saving_thread = threading.Thread()
        self._register_periodic_saving()

    def _register_periodic_saving(self):
        if not self.ckpt_configs[CONFIG_PERIODIC_SAVING]:
            return
        self._priodic_saving_thread = self._start_priodic_saving(self.ckpt_configs[CONFIG_PERIODIC_SAVING_INTERVAL])

    def _start_priodic_saving(self, interval: float) -> threading.Thread:
        timer = threading.Thread(target=self._priodic_saving, args=(interval,))
        timer.daemon = True
        timer.start()
        return timer

    def _priodic_saving(self, interval: float) -> None:
        while True:
            time.sleep(interval)
            logger.debug('Periodic saving started')
            self.async_save()
            logger.debug('Periodic saving finished')

    def pause_periodic_saving(self) -> None:
        self._acquire()

    def resume_periodic_saving(self) -> None:
        self._release()

    def _acquire(self) -> None:
        self._lock.acquire()

    def _release(self) -> None:
        self._lock.release()

    def _register_cleanup(self) -> None:
        # TODO(p0): Make sure cleanup function is executed correctly when using the agent.

        # Reference: https://stackoverflow.com/questions/23468042/the-invocation-of-signal-handler-and-atexit-handler-in-python  # noqa: E501

        def exit_handler():
            if self.ckpt_configs[CONFIG_ATEXIT_SAVING]:
                self.save()
                self._ckpt_mgr.release()

        atexit.register(exit_handler)

        current_handler = signal.getsignal(signal.SIGTERM)

        def handler(signum, frame) -> None:
            if callable(current_handler):
                current_handler(signum, frame)
            sys.exit()

        signal.signal(signal.SIGTERM, handler)

    def _reset(self) -> None:
        self._states = {}
        self._key_history = defaultdict(int)

    def _register_ckpt(self):
        settings = CheckpointCollectionSetting()
        ckpt_mgr_type = settings.ckpt_type
        ckpt_mgr_config = settings.ckpt_config
        self._ckpt_mgr = ckpt_mgr_type(StateManagerGroupCheckpointUID, **ckpt_mgr_config)

    def register(
        self,
        key: str,
        state_mgr_type: Type[BaseStateManager] = StateManager,
        auto_load: bool = True
    ) -> None:
        r""" Register a state manager in this group.

        :param key: A unique key of the state manager to register
        :param state_mgr_type: type of the state manager to register, defaults to `StateManager`
        :param auto_load: whether to automatically load the state using configured checkpoint manager,
            defaults to `True`

        :raises KeyError: duplicated state manager key
        :raises TypeError: invalid state manager type
        """

        if key in self._states:
            raise KeyError(f"Can not register manager with the same {key}")

        mgr = state_mgr_type(key)
        if not isinstance(mgr, BaseStateManager):
            raise TypeError(f"The type for state manger is not valid {type(mgr)}")

        if auto_load:
            states = self._ckpt_mgr.load()
            if states is not None:
                state = states.get(key, None)
                if state is not None:
                    mgr._load_impl(state)

        self._states[key] = mgr

    def list(self) -> List[str]:
        r"""
        :return: keys of registered state managers
        """
        return list(self._states.keys())

    def contain(self, key: str) -> bool:
        r""" Check whether the key exists.

        :param key: The key to check
        :return: `True` if key exists, `False` otherwise
        """

        return key in self._states

    def update(self, key: str, state: Any) -> None:
        r""" Update the managed state with the corresponding key.

        :param key: The key of the registered state manager
        :param state: The updated state
        """
        self._states[key].update(state)

    def get(self, key: str) -> Optional[State]:
        r""" Get the managed state with the corresponding key.

        :param key: The key of the registered state
        :return: The managed state, or `None` if no updated state
        """

        return self._states[key].get()

    def save(self) -> None:
        r""" Save managed states using the configured checkpoint manager in a lockstep. """

        states = self._get_states()
        if states:
            self._ckpt_mgr.save(states)

    def async_save(self) -> None:
        r""" Save managed states asynchronously using the configured checkpoint manager in a lockstep. """
        self._acquire()
        states = self._get_states(deep_copy=True)
        self._release()
        if states:
            logger.debug('Saving all the states')
            self._ckpt_mgr_save(states)
        else:
            logger.debug('There are no states to save')

    def _ckpt_mgr_save(self, states: Dict[str, State]) -> None:
        self._ckpt_mgr.save(states)
        self._ckpt_mgr.release()

    def _get_states(self, deep_copy: bool = False) -> Dict[str, State]:
        states = {}
        for k, mgr in self._states.items():
            state = mgr.get()
            if state is None:
                logger.debug('Can not save a checkpoint until all states exist')
                return {}

            if deep_copy and not isinstance(mgr, StateCopyManager):
                state = copy.deepcopy(state)
            states[k] = state
        return states

    def load(self) -> None:
        r""" Load managed states from the configured checkpoint manager in a lockstep. """

        states = self._ckpt_mgr.load()
        if states is not None:
            for k, state in states.items():
                self._states[k]._load_impl(state)

    def delete(self, key: str) -> None:
        r""" Delete managed states based on the key provided.

        :param key: The key to be deleted ('*' if all state)
        """

        if key == '*':
            for mgr in self._states.values():
                mgr.delete()

            self._reset()
        else:
            self._states[key].delete()
            del self._states[key]

    def keygen(self, obj: Any) -> str:
        r""" Generated an unique key based on an object.

        This generated key can be used as the key to register a state manager.

        :param obj: The object used to generate key
        :return: The generated key
        """

        key = type(obj).__name__
        retval = f'{key}.{self._key_history[key]}'
        self._key_history[key] += 1
        return retval
