import abc
from typing import Any


class Store(abc.ABC):
    client: Any

    @abc.abstractmethod
    def set(self, key, value) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self, key) -> bytes:
        raise NotImplementedError()

    @abc.abstractmethod
    def compare_set(self, key: str, expected_value: str, desired_value: str) -> bytes:
        raise NotImplementedError()

    @abc.abstractmethod
    def add(self, key, num: int) -> int:
        raise NotImplementedError()

    @abc.abstractmethod
    def wait(self, keys, override_timeout):
        raise NotImplementedError

    @abc.abstractmethod
    def check(self, keys) -> bool:
        raise NotImplementedError
