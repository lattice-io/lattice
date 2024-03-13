from .util import _Singleton
from .distributed.utils import (
    RequestType,
    CheckpointMessage
)
from .util import S3CheckpointHelper
from .constants import CHECKPOINT_TYPE, CHECKPOINT_CONFIG
from ..log import get_logger

import os
import re
import abc
import tempfile
import collections
import uuid
import zmq
from pathlib import Path
from filelock import FileLock
from urllib.parse import urlparse

from typing import Any, Callable, Dict, Tuple, List, Iterator, Union, Type, Optional, TypeVar

logger = get_logger(__name__)

T = TypeVar('T')


# Checkpoints
# -----------

class Checkpoint(abc.ABC):
    r""" The abstract base class of all types of checkpoints. """

    @abc.abstractmethod
    def __init__(self, target: Union[Type, Any], *args, **kwargs) -> None:
        self.kind: Type

    @abc.abstractmethod
    def exists(self, *args, **kwargs) -> bool:
        pass

    def __str__(self) -> str:
        return f'{self.__class__.__name__}'

    @staticmethod
    def parse(checkpoint_name: str) -> Tuple[str, str]:
        r""" Parse a checkpoint name to infer the original path and object type

        :param checkpoint_name: The full file path
        :return: The full name of the checkpoint with suffix and the type of the object saved
            in this checkpoint as a string

        :raises Exception: The `checkpoint_name` is invalid
        """

        try:
            original_file_name, type_str = checkpoint_name.rsplit(".", 1)
            assert original_file_name != '' and type_str != ''
        except Exception:
            raise Exception(f'Invalid local checkpoint file name {checkpoint_name}')
        return original_file_name, type_str


class LocalCheckpoint(Checkpoint):
    r""" Represent a checkpoint file on local file system

    :param target: A type of the object will be saved in this checkpoint. Can also pass an instance of this type
        and we can automatically figure out the target type.
    :param file_name: The path to the local checkpoint file. A suffix will be automatically added which describes the
        type of the object saved in this checkpoint.

    :raises KeyError: There is no registered saver for the target object type.
    """

    # TODO(p2): Remove "Bases" in Sphinx

    def __init__(self, target: Union[Type, Any], file_name: str) -> None:
        # If you want to create a concrete checkpoint object, you have to make
        # sure there is registered saver for it
        _, ty = LocalCheckpointSaver._lookup(target)
        self.kind = ty

        # Use object type as a suffix, which serves as a hint for deserialization
        self.path = f'{file_name}.{ty.__name__}'

    def exists(self) -> bool:
        r""" Check whether the checkpoint exists in the local file system.

        :return: `True` if key exists, `False` otherwise
        """
        return Path(self.path).exists()

    def __str__(self) -> str:
        return f'{super().__str__()}(path={self.path})'


class RemoteCheckpoint(Checkpoint):
    r""" Represents a checkpoint on the remote checkpoint service

    :param target: A type of the object will be saved in this checkpoint. Can also pass an instance of this type
        and we can automatically figure out the target type.
    :param job_id: A unique ID which is used to identify this job
    :param uid: The name of the UID of the Checkpoint Collection Manager that was used for this round of
        checkpoints
    :param key_name: The name of the remote checkpoint. A suffix will be automatically added which describes the
        type of the object saved in this checkpoint.

    :raises KeyError: There is no registered saver for the target object type
    """
    def __init__(self, target: Union[Type, Any], job_id: str, uid: str, key_name: str) -> None:
        _, ty = RemoteCheckpointSaver._lookup(target)
        self.kind = ty

        self.job_id = job_id
        self.uid = uid
        self.key_name = f'{key_name}.{ty.__name__}'

    def exists(self, socket: zmq.Socket) -> bool:
        r""" Check whether the checkpoint exists in the remote storage

        :return: `True` if key exists, `False` otherwise
        """
        msg = CheckpointMessage(RequestType.LIST, job_id=self.job_id, uid='', ckpt_name='', body=b'')
        socket.send(msg.encode_message())

        response = socket.recv()
        ckpt_response = CheckpointMessage.parse_message(response)
        ckpt_list_from_server = ckpt_response.body

        # No checkpoints found at all
        if not ckpt_list_from_server:
            return False

        try:
            key_set = ckpt_list_from_server[self.uid]
            return self.key_name in key_set
        except KeyError:
            return False

    def __str__(self) -> str:
        return f'{super().__str__()}(key={self.uid}/{self.key_name})'


class S3Checkpoint(Checkpoint):
    r""" Represents a checkpoint on the s3 checkpoint service

    :param target: A type of the object will be saved in this checkpoint. Can also pass an instance of this type
        and we can automatically figure out the target type.
    :param job_id: A unique ID which is used to identify this job
    :param uid: The name of the UID of the Checkpoint Collection Manager that was used for this round of
        checkpoints
    :param key_name: The name of the s3 checkpoint. A suffix will be automatically added which describes the
        type of the object saved in this checkpoint.

    :raises KeyError: There is no registered saver for the target object type
    """
    def __init__(self, target: Union[Type, Any], bucket_name: str, job_id: str, uid: str, key_name: str) -> None:
        _, ty = S3CheckpointSaver._lookup(target)
        self.kind = ty

        self.bucket_name = bucket_name
        self.job_id = job_id
        self.uid = uid
        self.key_name = f'{key_name}.{ty.__name__}'

    def exists(self) -> bool:
        r""" Check whether the checkpoint exists in the s3 storage

        :return: `True` if key exists, `False` otherwise
        """
        return S3CheckpointHelper.exists(self.bucket_name, self.job_id, self.uid, self.key_name)

    def __str__(self) -> str:
        return f'{super().__str__()}(key={self.uid}/{self.key_name})'

# Checkpoint processors
# ---------------------


class _CheckpointProcessor():
    # Dictionary format: <processor type name, <object type name, handler>>
    # NOTE: inherited static variable is shared by all inherited type objects
    _registered_handlers: Dict[Type, Dict[Type, Callable]] = collections.defaultdict(dict)

    @classmethod
    def _register(cls: Type, fn: Callable, t: Optional[Type] = None) -> None:
        r""" Register a handler (the implementation) of a concrete checkpoint processor to handle a specific class and
        all of its derived classes.
        """

        if t is None:
            t = object  # The type object as the base class of the class hierarchy

        if cls in cls._registered_handlers and t in cls._registered_handlers[cls]:
            logger.debug(f'Handler of processor {cls} for {t.__name__} has already been registered')
        else:
            if object in cls._registered_handlers[cls]:
                raise Exception(f'Processor {cls} can be used for all classes, '
                                f'and a specific handler for class {t.__name__} will not be used')

            cls._registered_handlers[cls][t] = fn
            logger.debug(f'Register handler of processor {cls.__name__} for class {t.__name__}')

    @classmethod
    def _lookup(cls: Type, obj: Union[Any, Type, str, None] = None) -> Tuple[Callable, Type]:
        r""" Lookup a registered handler of a concrete checkpoint processor and its associated base class.
        """

        handlers: Dict[Type, Callable] = cls._registered_handlers[cls]

        if obj is None:
            return (handlers[object], object)
        elif isinstance(obj, type):
            for ty, handler in handlers.items():
                if issubclass(obj, ty):
                    return (handler, ty)
            raise KeyError(f'Can not find registered handler {cls.__name__} for {obj.__name__}')
        elif isinstance(obj, str):
            for ty, handler in handlers.items():
                if ty.__name__ == obj:
                    return (handler, ty)
            raise KeyError(f'Can not find registered handler {cls.__name__} for {obj}')
        else:
            for ty, handler in handlers.items():
                if isinstance(obj, ty):
                    return (handler, ty)
            raise KeyError(f'Can not find registered handler {cls.__name__} for {type(obj).__name__}')


class _CheckpointSaver(_CheckpointProcessor):

    @classmethod
    def _invoke(cls, obj: Any, *args, **kwargs) -> Any:
        fn, _ = cls._lookup(obj)
        ckpt = fn(obj, *args, **kwargs)

        logger.debug(f'Save object {obj.__class__.__name__} to checkpoint {ckpt}')
        return ckpt


class _CheckpointLoader(_CheckpointProcessor):

    @classmethod
    def _invoke(cls, ckpt: Any, *args, **kwargs) -> Any:
        obj = ckpt.kind
        fn, _ = cls._lookup(obj)
        obj = fn(ckpt, *args, **kwargs)

        logger.debug(f'Load object {obj.__class__.__name__} from checkpoint {ckpt}')
        return obj


class _CheckpointDeleter(_CheckpointProcessor):

    @classmethod
    def _invoke(cls, ckpt: Any, *args, **kwargs) -> None:
        fn, _ = cls._lookup()
        fn(ckpt, *args, **kwargs)

        logger.debug(f'Delete checkpoint {ckpt}')


class LocalCheckpointSaver(_CheckpointSaver):

    @classmethod
    def register_handler(cls, t: Type[T], fn: Callable[[T, str], LocalCheckpoint]) -> None:
        super()._register(fn, t)

    @classmethod
    def invoke(cls, obj: Any, *args, **kwargs) -> LocalCheckpoint:
        return super()._invoke(obj, *args, **kwargs)


class LocalCheckpointLoader(_CheckpointLoader):

    @classmethod
    def register_handler(cls, t: Type[T], fn: Callable[[LocalCheckpoint], T]) -> None:
        super()._register(fn, t)

    @classmethod
    def invoke(cls, ckpt: LocalCheckpoint, *args, **kwargs) -> Any:
        return super()._invoke(ckpt, *args, **kwargs)


class LocalCheckpointDeleter(_CheckpointDeleter):

    @classmethod
    def register_handler(cls, fn: Callable[[LocalCheckpoint], None]) -> None:
        super()._register(fn)

    @classmethod
    def invoke(cls, ckpt: LocalCheckpoint, *args, **kwargs) -> None:
        return super()._invoke(ckpt, *args, **kwargs)


class RemoteCheckpointSaver(_CheckpointSaver):

    @classmethod
    def register_handler(cls, t: Type[T], fn: Callable[[T, zmq.Socket, str, str, str], RemoteCheckpoint]) -> None:
        super()._register(fn, t)

    @classmethod
    def invoke(cls, ob: Any, *args, **kwargs) -> RemoteCheckpoint:
        return super()._invoke(ob, *args, **kwargs)


class RemoteCheckpointLoader(_CheckpointLoader):

    @classmethod
    def register_handler(cls, t: Type[T], fn: Callable[[RemoteCheckpoint, zmq.Socket], T]) -> None:
        super()._register(fn, t)

    @classmethod
    def invoke(cls, ckpt: RemoteCheckpoint, *args, **kwargs) -> Any:
        return super()._invoke(ckpt, *args, **kwargs)


class RemoteCheckpointDeleter(_CheckpointDeleter):

    @classmethod
    def register_handler(cls, fn: Callable[[RemoteCheckpoint, zmq.Socket], None]) -> None:
        super()._register(fn)

    @classmethod
    def invoke(cls, ckpt: RemoteCheckpoint, *args, **kwargs) -> None:
        return super()._invoke(ckpt, *args, **kwargs)


class S3CheckpointSaver(_CheckpointSaver):

    @classmethod
    def register_handler(cls, t: Type[T], fn: Callable[[T, str, str, str, str], S3Checkpoint]) -> None:
        super()._register(fn, t)

    @classmethod
    def invoke(cls, ob: Any, *args, **kwargs) -> S3Checkpoint:
        return super()._invoke(ob, *args, **kwargs)


class S3CheckpointLoader(_CheckpointLoader):

    @classmethod
    def register_handler(cls, t: Type[T], fn: Callable[[S3Checkpoint], T]) -> None:
        super()._register(fn, t)

    @classmethod
    def invoke(cls, ckpt: S3Checkpoint, *args, **kwargs) -> Any:
        return super()._invoke(ckpt, *args, **kwargs)


class S3CheckpointDeleter(_CheckpointDeleter):

    @classmethod
    def register_handler(cls, fn: Callable[[S3Checkpoint], None]) -> None:
        super()._register(fn)

    @classmethod
    def invoke(cls, ckpt: S3Checkpoint, *args, **kwargs) -> None:
        return super()._invoke(ckpt, *args, **kwargs)


def local_checkpoint_saver(type: Type[T]):
    r""" A decorator with arguments to register a handler for saving a local checkpoint

    Example usage:

    .. code-block:: python

        @local_checkpoint_saver(type=T)
        def handler(obj: T, path: str) -> None:
            ...
    """
    def inner(func: Callable[[T, str], None]) -> Callable[[T, str], LocalCheckpoint]:
        def wrapper(obj: T, path: str) -> LocalCheckpoint:
            ckpt = LocalCheckpoint(obj, path)
            func(obj, ckpt.path)
            return ckpt

        LocalCheckpointSaver.register_handler(type, wrapper)
        return wrapper
    return inner


def local_checkpoint_loader(type: Type[T]):
    r""" A decorator with arguments to register a handler for loading a local checkpoint

    Example usage:

    .. code-block:: python

        @local_checkpoint_loader(type=T)
        def handler(path: str) -> T:
            ...
    """
    def inner(func: Callable[[str], T]) -> Callable[[LocalCheckpoint], T]:
        def wrapper(ckpt: LocalCheckpoint) -> T:
            obj = func(ckpt.path)
            return obj

        LocalCheckpointLoader.register_handler(type, wrapper)
        return wrapper
    return inner


def local_checkpoint_deleter(func: Callable[[str], None]):
    r""" A decorator to register a handler for deleting a local checkpoint

    Example usage:

    .. code-block:: python

        @local_checkpoint_deleter
        def handler(path: str) -> None:
            ...
    """
    def wrapper(ckpt: LocalCheckpoint) -> None:
        func(ckpt.path)

    LocalCheckpointDeleter.register_handler(wrapper)
    return wrapper


def remote_checkpoint_saver(type: Type[T]):
    r""" A decorator with argument to register a handler for saving a remote checkpoint

    Example usage:

    .. code-block:: python

        @remote_checkpoint_saver(type=T)
        def handler(obj: T, socket: zmq.Socket, job_id: str, uid: str, key: str) -> None:
            ...
    """
    def inner(func: Callable[[T, zmq.Socket, str, str, str], None]) -> \
            Callable[[T, zmq.Socket, str, str, str], RemoteCheckpoint]:
        def wrapper(obj: T, socket: zmq.Socket, job_id: str, uid: str, key: str):
            ckpt = RemoteCheckpoint(obj, job_id=job_id, uid=uid, key_name=key)
            func(obj, socket, job_id, uid, ckpt.key_name)

            return ckpt

        RemoteCheckpointSaver.register_handler(type, wrapper)
        return wrapper

    return inner


def remote_checkpoint_loader(type: Type[T]):
    r""" A decorator with arguments to register a handler for loading a remote checkpoint

    Example usage:

    .. code-block:: python

        @remote_checkpoint_loader(type=T)
        def handler(socket: zmq.Socket, job_id: str, uid: str, key: str) -> T:
            ...
    """
    def inner(func: Callable[[zmq.Socket, str, str, str], T]) -> Callable[[RemoteCheckpoint, zmq.Socket], T]:
        def wrapper(ckpt: RemoteCheckpoint, socket: zmq.Socket) -> T:
            obj = func(socket, ckpt.job_id, ckpt.uid, ckpt.key_name)
            return obj

        RemoteCheckpointLoader.register_handler(type, wrapper)
        return wrapper

    return inner


def remote_checkpoint_deleter(func: Callable[[zmq.Socket, str, str, str], None]):
    r""" A decorator to register a handler for deleting a remote checkpoint

    Example usage:

    .. code-block:: python

        @remote_checkpoint_deleter
        def handler(socket: zmq.Socket, job_id: str, uid: str, key: str) -> None:
            ...
    """
    def wrapper(ckpt: RemoteCheckpoint, socket: zmq.Socket) -> None:
        func(socket, ckpt.job_id, ckpt.uid, ckpt.key_name)

    RemoteCheckpointDeleter.register_handler(wrapper)
    return wrapper


def s3_checkpoint_saver(type: Type[T]):
    r""" A decorator with argument to register a handler for saving a s3 checkpoint

    Example usage:

    .. code-block:: python

        @s3_checkpoint_saver(type=T)
        def handler(obj: T, bucket_name: str, job_id: str, uid: str, key: str) -> None:
            ...
    """
    def inner(func: Callable[[T, str, str, str, str], None]) -> \
            Callable[[T, str, str, str, str], S3Checkpoint]:
        def wrapper(obj: T, bucket_name: str, job_id: str, uid: str, key: str):
            ckpt = S3Checkpoint(obj, bucket_name=bucket_name, job_id=job_id, uid=uid, key_name=key)
            func(obj, bucket_name, job_id, uid, ckpt.key_name)

            return ckpt

        S3CheckpointSaver.register_handler(type, wrapper)
        return wrapper

    return inner


def s3_checkpoint_loader(type: Type[T]):
    r""" A decorator with arguments to register a handler for loading a s3 checkpoint

    Example usage:

    .. code-block:: python

        @s3_checkpoint_loader(type=T)
        def handler(bucket_name: str, job_id: str, uid: str, key: str) -> T:
            ...
    """
    def inner(func: Callable[[str, str, str, str], T]) -> Callable[[S3Checkpoint], T]:
        def wrapper(ckpt: S3Checkpoint) -> T:
            obj = func(ckpt.bucket_name, ckpt.job_id, ckpt.uid, ckpt.key_name)
            return obj

        S3CheckpointLoader.register_handler(type, wrapper)
        return wrapper

    return inner


def s3_checkpoint_deleter(func: Callable[[str, str, str, str], None]):
    r""" A decorator to register a handler for deleting a s3 checkpoint

    Example usage:

    .. code-block:: python

        @s3_checkpoint_deleter
        def handler(bucket_name: str, job_id: str, uid: str, key: str) -> None:
            ...
    """
    def wrapper(ckpt: S3Checkpoint) -> None:
        func(ckpt.bucket_name, ckpt.job_id, ckpt.uid, ckpt.key_name)

    S3CheckpointDeleter.register_handler(wrapper)
    return wrapper


# Checkpoint manager
# ------------------

class BaseCheckpointManager(abc.ABC):
    r""" An abstract base class for checkpoint managers.

    :param uid: Will be used to identify checkpoints created by this manager.
    """

    def __init__(self, uid: str) -> None:
        self._uid = uid
        self._ckpt_list: List[Any] = []
        self._counter: int = 0

        self._validate()
        self._discover()

    @abc.abstractmethod
    def _create_checkpoint(self, type_str: str, uid: str, name: str) -> Checkpoint:
        pass

    @abc.abstractmethod
    def _validate(self) -> None:
        pass

    @abc.abstractmethod
    def _discover(self) -> None:
        pass

    @abc.abstractmethod
    def _save_impl(self, obj: Any, ckpt_uid: str) -> Any:
        pass

    @abc.abstractmethod
    def _load_impl(self, ckpt: Any) -> Any:
        pass

    @abc.abstractmethod
    def get_configs(self) -> Dict[str, Any]:
        pass

    def _gen_ckpt_uid(self) -> str:
        # Format: <ckpt mgr type>_<ckpt mgr uid>_<counter>
        retval = f'{self}_{self._counter:06}'
        self._counter += 1
        return retval

    def _set_ckpt_uid(self, counter: int) -> None:
        self._counter = counter
        self._counter += 1

    def _match_ckpt_uid(self, name: str, raise_expt: bool = False) -> int:
        pattern = re.compile(f'^{self}_[0-9]{{6}}$')

        if pattern.match(name) is None:
            msg = f'Pattern {pattern} can not match {name}'
            if raise_expt:
                raise Exception(msg)
            logger.debug(msg)
            return -1

        _, counter = name.split('_')
        return int(counter)

    def list(self) -> Iterator[Checkpoint]:
        r"""
        :return: An iterator of managed checkpoints
        """

        return iter(self._ckpt_list)

    def len(self) -> int:
        r"""
        :return: The number of managed checkpoints
        """

        return len(self._ckpt_list)

    def save(self, obj: Any) -> None:
        r"""
        :param obj: The object to save
        """

        ckpt = self._save_impl(obj, self._gen_ckpt_uid())
        self._ckpt_list.append(ckpt)

    def load(self) -> Optional[Any]:
        r"""
        :return: The loaded object, or `None` if there is no managed checkpoints
        """

        if len(self._ckpt_list) == 0:
            logger.debug(f'Can not find existing checkpoint in {self}')
            return None

        while True:
            try:
                # Load the most recent checkpoint
                ckpt = self._ckpt_list[-1]
                obj = self._load_impl(ckpt)

                # If succeeds, directly return the object
                break

            except Exception as e:
                # If load failed, try to load the previous one
                ckpt = self._ckpt_list.pop()
                logger.info(f'Unable to load object from checkpoint {ckpt} due to exception: {e}')

                # Until there is no valid checkpoint
                if len(self._ckpt_list) == 0:
                    obj = None
                    break

        return obj

    def __str__(self) -> str:
        return f'{self.__class__.__name__}:{self._uid}'


class BaseCheckpointCollectionManager(BaseCheckpointManager):
    r""" An abstract base class for checkpoint collection managers.

    Checkpoint collection includes several checkpoints that are saved and loaded as a transaction. It fits the need
    for state manager group. This type of manager should provide the ability to handle distributed replicated
    checkpoints with a write lock.
    """

    def __init__(self, uid: str) -> None:
        super().__init__(uid)

        self.acquired: bool = False
        self._lock: Any = None

    def __del__(self):
        if self.acquired:
            self._release()

    @abc.abstractmethod
    def _acquire(self) -> None:
        pass

    @abc.abstractmethod
    def _release(self) -> None:
        pass

    def acquire(self) -> None:
        r""" Acquire the write lock. """

        try:
            self._acquire()
            self.acquired = True
            logger.debug(f'Process {os.getpid()} acquired write lock')
        except Exception:
            logger.debug(f'Process {os.getpid()} failed to acquire write lock')

    def release(self) -> None:
        r""" Release the write lock. """

        try:
            if not self.acquired:
                return
            self._release()
            logger.debug(f'Process {os.getpid()} released write lock')
        except Exception:
            logger.debug(f'Process {os.getpid()} failed to release write lock')

    def save(self, objs: Dict[str, Any]) -> None:
        r"""
        :param objs: The dictionary of objects to save
        """

        # Lazily acquire lock before each save.
        self.acquire()
        if not self.acquired:
            return

        return super().save(objs)

    def load(self) -> Optional[Dict[str, Any]]:
        r"""
        :return: The loaded dictionary of objects, or `None` if there is no managed checkpoint collections.
        """

        return super().load()

    def _parse_discovered_checkpoints(self, discovery_location: str, ckpt_list: Dict[str, List[str]]) -> None:
        valid_ckpt_files: Dict[int, Dict[str, Checkpoint]] = {}

        for uid in ckpt_list:
            try:
                ckpt_key = self._match_ckpt_uid(uid, raise_expt=True)

                ckpts = {}
                ckpt_files = ckpt_list[uid]
                for ckpt_name in ckpt_files:
                    key_name, type_str = Checkpoint.parse(ckpt_name)

                    ckpt = self._create_checkpoint(type_str, uid, key_name)

                    ckpts[key_name] = ckpt

                if not ckpts:
                    raise Exception("No valid checkpoints found for", uid)

                valid_ckpt_files[ckpt_key] = ckpts
            except Exception as e:
                logger.debug(f'Checkpoint discovery skips {uid} due to: {e}')
                continue

        if valid_ckpt_files:
            for _, ckpts in sorted(valid_ckpt_files.items()):
                self._ckpt_list.append(ckpts)
                logger.debug(f'Discover existing ckpt {[str(c) for c in ckpts]}')

            max_key = max(list(valid_ckpt_files.keys()))
            self._set_ckpt_uid(int(max_key))
        else:
            logger.debug(f'Did not discover any existing ckpt for {discovery_location}')


class LocalCheckpointManager(BaseCheckpointManager):
    r""" Manage local checkpoints. """

    def __init__(self,
                 uid: str,
                 root: str,
                 atexit_saving: str = 'enabled',
                 periodic_saving: str = 'disabled',
                 periodic_saving_interval: Optional[str] = None) -> None:
        self._root: str = root
        self._atexit_saving: bool = atexit_saving.lower() == 'enabled'
        self._periodic_saving: bool = periodic_saving.lower() == 'enabled'
        self._periodic_saving_interval: Optional[float] = None
        if self._periodic_saving:
            if not periodic_saving_interval:
                raise ValueError('periodic_saving_interval must be specified when periodic_saving is enabled')
            self._periodic_saving_interval = float(periodic_saving_interval)
        self._ckpt_list: List[LocalCheckpoint]

        super().__init__(uid)

    def get_configs(self) -> Dict[str, Any]:
        return {
            'root': self._root,
            'atexit_saving': self._atexit_saving,
            'periodic_saving': self._periodic_saving,
            'periodic_saving_interval': self._periodic_saving_interval
        }

    def _create_checkpoint(self, type_str: str, d: str, file_name: str) -> Checkpoint:
        file_path = os.path.join(self._root, d, file_name)
        return LocalCheckpoint(type_str, file_path)

    def _validate(self) -> None:
        root_path = Path(self._root)

        # Check whether we need to mkdir
        if not root_path.exists():
            root_path.mkdir(parents=True, exist_ok=True)

        # If not, check whether we have the permission
        else:
            # TODO(p1): Check read/write permissions
            if not os.access(root_path, os.R_OK | os.W_OK):
                raise PermissionError(f'Unable to create checkpoint manager for root path {self._root} due to '
                                      f'insufficient permissions')

    def _discover(self) -> None:
        valid_ckpt_files: Dict[int, LocalCheckpoint] = {}

        root = Path(self._root)
        for f in root.iterdir():
            try:
                file_name, type_str = LocalCheckpoint.parse(f.name)

                ckpt_key = self._match_ckpt_uid(file_name, raise_expt=True)

                path = str(root / file_name)
                ckpt = LocalCheckpoint(type_str, path)

                valid_ckpt_files[ckpt_key] = ckpt
            except Exception as e:
                logger.debug(f'Checkpoint discovery skips {f} due to: {e}')
                continue

        if valid_ckpt_files:
            for _, ckpt in sorted(valid_ckpt_files.items()):
                self._ckpt_list.append(ckpt)
                logger.debug(f'Discover existing ckpt {ckpt}')

            max_key = max(list(valid_ckpt_files.keys()))
            self._set_ckpt_uid(max_key)
        else:
            logger.debug(f'Can not discover existing ckpt at {self._root}')

    def _save_impl(self, obj: Any, ckpt_uid: str) -> LocalCheckpoint:
        path = str(Path(self._root) / ckpt_uid)
        return LocalCheckpointSaver.invoke(obj, path)

    def _load_impl(self, ckpt: LocalCheckpoint) -> Any:
        return LocalCheckpointLoader.invoke(ckpt)


class LocalCheckpointCollectionManager(BaseCheckpointCollectionManager):
    r""" Manage local checkpoint collections. """

    def __init__(self,
                 uid: str,
                 root: str,
                 atexit_saving: str = 'enabled',
                 periodic_saving: str = 'disabled',
                 periodic_saving_interval: Optional[str] = None) -> None:
        self._root: str = root
        self._atexit_saving: bool = atexit_saving.lower() == 'enabled'
        self._periodic_saving: bool = periodic_saving.lower() == 'enabled'
        self._periodic_saving_interval: Optional[float] = None
        if self._periodic_saving:
            if not periodic_saving_interval:
                raise ValueError('periodic_saving_interval must be specified when periodic_saving is enabled')
            self._periodic_saving_interval = float(periodic_saving_interval)
        self._ckpt_list: List[Dict[str, LocalCheckpoint]]

        super().__init__(uid)

        lock_path = str(Path(self._root) / 'lock')
        self._lock: FileLock = FileLock(lock_path)

    def get_configs(self) -> Dict[str, Any]:
        return {
            'root': self._root,
            'atexit_saving': self._atexit_saving,
            'periodic_saving': self._periodic_saving,
            'periodic_saving_interval': self._periodic_saving_interval
        }

    def _create_checkpoint(self, type_str: str, d: str, file_name: str) -> LocalCheckpoint:
        file_path = os.path.join(self._root, d, file_name)
        return LocalCheckpoint(type_str, file_path)

    def _acquire(self) -> None:
        self._lock.acquire(blocking=False)

    def _release(self):
        self._lock.release()

    def _validate(self) -> None:
        root_path = Path(self._root)

        # Check whether we need to mkdir
        if not root_path.exists():
            root_path.mkdir(parents=True, exist_ok=True)

        # If not, check whether we have the permission
        else:
            # TODO(p1): Check read/write permissions
            self.acquired = False  # __del__ Throws AttributeError without
            if not os.access(root_path, os.R_OK | os.W_OK):
                raise PermissionError(f'Unable to create collection for root path {self._root} due to '
                                      f'insufficient permissions')

    def _discover(self) -> None:
        root = Path(self._root)
        ckpt_list: Dict[str, List[str]] = collections.defaultdict(lambda: list())
        # Convert the directory structure to Dict[str, List[str]]
        # for compatibility
        for d in root.iterdir():
            try:
                if not d.is_dir():
                    raise Exception("Invalid file type")

                ckpts = []
                for file in d.iterdir():
                    ckpts.append(file.name)

                if not ckpts:
                    raise Exception("Empty directory")

                ckpt_list[d.name] = ckpts
            except Exception as e:
                logger.debug(f'Checkpoint discovery skips {d} due to: {e}')
                continue

        # Run the actual checkpoint discovery
        self._parse_discovered_checkpoints(self._root, ckpt_list)

    def _save_impl(self, objs: Dict[str, Any], ckpt_uid: str) -> Dict[str, LocalCheckpoint]:
        root = Path(self._root) / ckpt_uid
        root.mkdir(parents=True, exist_ok=True)

        retval = {}
        for k, obj in objs.items():
            path = str(root / k)
            retval[k] = LocalCheckpointSaver.invoke(obj, path)

        return retval

    def _load_impl(self, ckpts: Dict[str, LocalCheckpoint]) -> Dict[str, Any]:
        retval = {}
        for k, ckpt in ckpts.items():
            retval[k] = LocalCheckpointLoader.invoke(ckpt)

        return retval


class RemoteCheckpointManager(BaseCheckpointManager):
    r""" Manage remote checkpoints. """
    def __init__(self,
                 uid: str,
                 job_id: str,
                 ckpt_service_endpoint: str,
                 ckpt_service_port: str = '5555',
                 atexit_saving: str = 'enabled',
                 periodic_saving: str = 'disabled',
                 periodic_saving_interval: Optional[str] = None) -> None:
        self._job_id = job_id
        self._ckpt_service_endpoint = ckpt_service_endpoint
        self._ckpt_list: List[Dict[str, RemoteCheckpoint]]
        self._ckpt_service_port = ckpt_service_port

        self._atexit_saving: bool = atexit_saving.lower() == 'enabled'
        self._periodic_saving: bool = periodic_saving.lower() == 'enabled'
        self._periodic_saving_interval: Optional[float] = None
        if self._periodic_saving:
            if not periodic_saving_interval:
                raise ValueError('periodic_saving_interval must be specified when periodic_saving is enabled')
            self._periodic_saving_interval = float(periodic_saving_interval)

    def get_configs(self) -> Dict[str, Any]:
        return {
            'job_id': self._job_id,
            'ckpt_service_endpoint': self._ckpt_service_endpoint,
            'ckpt_service_port': self._ckpt_service_port,
            'atexit_saving': self._atexit_saving,
            'periodic_saving': self._periodic_saving,
            'periodic_saving_interval': self._periodic_saving_interval
        }

    def _create_checkpoint(self, type_str: str, uid: str, key_name: str) -> Checkpoint:
        return RemoteCheckpoint(type_str, self._job_id, uid, key_name)

    def _validate(self) -> None:
        pass

    def _discover(self) -> None:
        pass

    def _save_impl(self, obj: Any, ckpt_uid: str) -> Any:
        pass

    def _load_impl(self, ckpt: Any) -> Any:
        pass


class RemoteCheckpointCollectionManager(BaseCheckpointCollectionManager):
    r""" Manage remote checkpoint collections. """
    def __init__(self,
                 uid: str,
                 job_id: str,
                 ckpt_service_endpoint: str,
                 ckpt_service_port: str = '5555',
                 atexit_saving: str = 'enabled',
                 periodic_saving: str = 'disabled',
                 periodic_saving_interval: Optional[str] = None):
        # TODO(p1): Add strategy option and frequency options to checkpoint config
        self._job_id = job_id
        self._ckpt_service_endpoint = ckpt_service_endpoint
        self._ckpt_list: List[Dict[str, RemoteCheckpoint]]

        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.REQ)
        self._ckpt_service_port = ckpt_service_port
        self._socket.connect(f'tcp://{self._ckpt_service_endpoint}:{self._ckpt_service_port}')

        self._atexit_saving: bool = atexit_saving.lower() == 'enabled'
        self._periodic_saving: bool = periodic_saving.lower() == 'enabled'
        self._periodic_saving_interval: Optional[float] = None
        if self._periodic_saving:
            if not periodic_saving_interval:
                raise ValueError('periodic_saving_interval must be specified when periodic_saving is enabled')
            self._periodic_saving_interval = float(periodic_saving_interval)

        super().__init__(uid)

        # TODO(p0): Figure out lock implementation when using TCP listener?
        # self._lock = ??

    def get_configs(self) -> Dict[str, Any]:
        return {
            'job_id': self._job_id,
            'ckpt_service_endpoint': self._ckpt_service_endpoint,
            'ckpt_service_port': self._ckpt_service_port,
            'atexit_saving': self._atexit_saving,
            'periodic_saving': self._periodic_saving,
            'periodic_saving_interval': self._periodic_saving_interval
        }

    def _create_checkpoint(self, type_str: str, uid: str, key_name: str) -> RemoteCheckpoint:
        return RemoteCheckpoint(type_str, self._job_id, uid, key_name)

    def _acquire(self) -> None:
        # TODO(p0)
        pass

    def _release(self) -> None:
        # TODO(p0)
        pass

    def _validate(self) -> None:
        msg = CheckpointMessage(RequestType.PING, job_id=self._job_id, uid='', ckpt_name='', body=b'')
        self._socket.send(msg.encode_message())

        response = self._socket.recv()
        ckpt_response = CheckpointMessage.parse_message(response)
        assert ckpt_response.req_type == RequestType.PING \
            and ckpt_response.job_id == self._job_id \
            and ckpt_response.body == b'ACK'

    def _discover(self) -> None:
        msg = CheckpointMessage(RequestType.LIST, job_id=self._job_id, uid='', ckpt_name='', body=b'')
        self._socket.send(msg.encode_message())

        response = self._socket.recv()
        ckpt_response = CheckpointMessage.parse_message(response)
        ckpt_list_from_server = ckpt_response.body

        # ckpt_list_from_server: Dict[str, List[str]]
        if not ckpt_list_from_server:
            logger.debug(f'No existing checkpoints found for job ID {self._job_id}')
            return

        self._parse_discovered_checkpoints(self._job_id, ckpt_list_from_server)

    def _save_impl(self, objs: Dict[str, Any], ckpt_uid: str) -> Dict[str, RemoteCheckpoint]:
        retval: Dict[str, RemoteCheckpoint] = {}
        for k, obj in objs.items():
            retval[k] = RemoteCheckpointSaver.invoke(obj, self._socket, self._job_id, ckpt_uid, k)

        return retval

    def _load_impl(self, ckpts: Any) -> Any:
        retval = {}
        for k, ckpt in ckpts.items():
            retval[k] = RemoteCheckpointLoader.invoke(ckpt, self._socket)

        return retval


class S3CheckpointManager(BaseCheckpointManager):
    r""" Manage s3 checkpoints. """
    def __init__(self,
                 uid: str,
                 root: str,
                 atexit_saving: str = 'enabled',
                 periodic_saving: str = 'disabled',
                 periodic_saving_interval: Optional[str] = None) -> None:
        parsed_url = urlparse(root)
        self._bucket_name = parsed_url.netloc
        self._job_id = parsed_url.path.strip('/')
        self._ckpt_list: List[Dict[str, S3Checkpoint]]

        self._atexit_saving: bool = atexit_saving.lower() == 'enabled'
        self._periodic_saving: bool = periodic_saving.lower() == 'enabled'
        self._periodic_saving_interval: Optional[float] = None
        if self._periodic_saving:
            if not periodic_saving_interval:
                raise ValueError('periodic_saving_interval must be specified when periodic_saving is enabled')
            self._periodic_saving_interval = float(periodic_saving_interval)

    def get_configs(self) -> Dict[str, Any]:
        return {
            'bucket_name': self._bucket_name,
            'job_id': self._job_id,
            'atexit_saving': self._atexit_saving,
            'periodic_saving': self._periodic_saving,
            'periodic_saving_interval': self._periodic_saving_interval
        }

    def _create_checkpoint(self, type_str: str, uid: str, key_name: str) -> Checkpoint:
        return S3Checkpoint(type_str, self._bucket_name, self._job_id, uid, key_name)

    def _validate(self) -> None:
        pass

    def _discover(self) -> None:
        pass

    def _save_impl(self, obj: Any, ckpt_uid: str) -> Any:
        pass

    def _load_impl(self, ckpt: Any) -> Any:
        pass


class S3CheckpointCollectionManager(BaseCheckpointCollectionManager):
    r""" Manage s3 checkpoint collections. """
    def __init__(self,
                 uid: str,
                 root: str,
                 atexit_saving: str = 'enabled',
                 periodic_saving: str = 'disabled',
                 periodic_saving_interval: Optional[str] = None):
        parsed_url = urlparse(root)
        self._bucket_name = parsed_url.netloc
        self._job_id = parsed_url.path.strip('/')
        self._ckpt_list: List[Dict[str, S3Checkpoint]]

        self._atexit_saving: bool = atexit_saving.lower() == 'enabled'
        self._periodic_saving: bool = periodic_saving.lower() == 'enabled'
        self._periodic_saving_interval: Optional[float] = None
        if self._periodic_saving:
            if not periodic_saving_interval:
                raise ValueError('periodic_saving_interval must be specified when periodic_saving is enabled')
            self._periodic_saving_interval = float(periodic_saving_interval)

        super().__init__(uid)

    def get_configs(self) -> Dict[str, Any]:
        return {
            'bucket_name': self._bucket_name,
            'job_id': self._job_id,
            'atexit_saving': self._atexit_saving,
            'periodic_saving': self._periodic_saving,
            'periodic_saving_interval': self._periodic_saving_interval
        }

    def _create_checkpoint(self, type_str: str, uid: str, key_name: str) -> S3Checkpoint:
        return S3Checkpoint(type_str, self._bucket_name, self._job_id, uid, key_name)

    def _acquire(self) -> None:
        # TODO(p0)
        pass

    def _release(self) -> None:
        # TODO(p0)
        pass

    def _validate(self) -> None:
        assert S3CheckpointHelper.ping(self._bucket_name)

    def _discover(self) -> None:
        ckpt_list_from_server = S3CheckpointHelper.list(self._bucket_name, self._job_id)

        if not ckpt_list_from_server:
            logger.debug(f'No existing checkpoints found for job ID {self._job_id}')
            return

        self._parse_discovered_checkpoints(self._job_id, ckpt_list_from_server)

    def _save_impl(self, objs: Dict[str, Any], ckpt_uid: str) -> Dict[str, S3Checkpoint]:
        retval: Dict[str, S3Checkpoint] = {}
        for k, obj in objs.items():
            retval[k] = S3CheckpointSaver.invoke(obj, self._bucket_name, self._job_id, ckpt_uid, k)

        return retval

    def _load_impl(self, ckpts: Any) -> Any:
        retval = {}
        for k, ckpt in ckpts.items():
            retval[k] = S3CheckpointLoader.invoke(ckpt)

        return retval


# Checkpoint settings
# -------------------

class CheckpointSetting(metaclass=_Singleton):
    r""" The setting for checkpoint managers.

    The checkpoint setting is a singleton. It parses checkpoint types and configurations from env var.
    """

    def __init__(self) -> None:
        self._ckpt_mgr_type: Type[BaseCheckpointManager]
        self._ckpt_mgr_config: Dict[str, str]

        self._parse_env()
        self._validate()

        logger.info(
            f'Use checkpoint manager setting {self._ckpt_mgr_type.__name__} with config {self._ckpt_mgr_config}')

    @property
    def ckpt_type(self) -> Type[BaseCheckpointManager]:
        r"""
        :return: Type object of the selected checkpoint manager.
        """
        return self._ckpt_mgr_type

    @property
    def ckpt_config(self) -> Dict[str, str]:
        r"""
        :return: Configuration for the selected checkpoint manager as a dictionary.
        """
        return self._ckpt_mgr_config

    # TODO: Simplify this implementation
    def _parse_env(self) -> None:
        ckpt_mgr_type_str = os.environ.get(CHECKPOINT_TYPE, '').lower()
        ckpt_mgr_type = self._get_ckpt_mgr_type(ckpt_mgr_type_str)

        if ckpt_mgr_type is None:
            ckpt_mgr_type_str = '(Empty)' if len(ckpt_mgr_type_str) == 0 else ckpt_mgr_type_str
            logger.debug(f'Get invalid checkpoint type {ckpt_mgr_type_str}')
            self._set_default()
            return

        ckpt_mgr_config_str = os.environ.get(CHECKPOINT_CONFIG, '')
        ckpt_mgr_config = self._get_ckpt_mgr_config(ckpt_mgr_config_str)

        if ckpt_mgr_config is None:
            ckpt_mgr_config_str = '(Empty)' if len(ckpt_mgr_config_str) == 0 else ckpt_mgr_config_str
            logger.debug(f'Get invalid checkpoint config {ckpt_mgr_config_str}')
            self._set_default()
            return

        self._ckpt_mgr_type = ckpt_mgr_type
        self._ckpt_mgr_config = ckpt_mgr_config

    def _validate(self) -> None:
        try:
            # Use a random uuid for test
            self._ckpt_mgr_type(uid=str(uuid.uuid4()), **self._ckpt_mgr_config)
        except Exception as e:
            raise Exception(
                f'Unable to create checkpoint manager '
                f'{self._ckpt_mgr_type.__name__} with config {self._ckpt_mgr_config} '
                f'due to {e}')

    def _set_default(self) -> None:
        self._ckpt_mgr_type = self._get_default_ckpt_mgr_type()
        self._ckpt_mgr_config = self._get_default_ckpt_mgr_config()

    def _get_ckpt_mgr_type(self, key: str) -> Optional[Type[BaseCheckpointManager]]:
        ckpt_mgr_types: Dict[str, Type[BaseCheckpointManager]] = {
            'local': LocalCheckpointManager,
            'remote': RemoteCheckpointManager,
            's3': S3CheckpointManager,
        }
        return ckpt_mgr_types.get(key, None)

    def _get_ckpt_mgr_config(self, config_str: str) -> Optional[Dict[str, str]]:
        # Comma-separated key value pairs
        pattern = re.compile(r'^([^=]+=[^=]+)(,[^=]+=[^=]+)*$')
        if not pattern.match(config_str):
            return None
        return dict(map(lambda x: x.split('='), config_str.split(',')))

    def _get_default_ckpt_mgr_type(self) -> Type[BaseCheckpointManager]:
        return LocalCheckpointManager

    def _get_default_ckpt_mgr_config(self) -> Dict[str, str]:
        return {'root': tempfile.mkdtemp()}


class CheckpointCollectionSetting(CheckpointSetting):
    r""" The setting for checkpoint collection managers.

    The checkpoint collection setting is a singleton. It parses checkpoint types and configurations from env var.
    """

    def __init__(self) -> None:
        super().__init__()

        self._ckpt_mgr_type: Type[BaseCheckpointCollectionManager]

    def _get_ckpt_mgr_type(self, key: str) -> Optional[Type[BaseCheckpointCollectionManager]]:
        ckpt_mgr_types: Dict[str, Type[BaseCheckpointCollectionManager]] = {
            'local': LocalCheckpointCollectionManager,
            'remote': RemoteCheckpointCollectionManager,
            's3': S3CheckpointCollectionManager,
        }
        return ckpt_mgr_types.get(key, None)

    def _get_default_ckpt_mgr_type(self) -> Type[BaseCheckpointCollectionManager]:
        return LocalCheckpointCollectionManager
