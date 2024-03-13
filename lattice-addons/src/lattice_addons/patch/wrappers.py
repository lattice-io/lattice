from typing import Any


class UniversalWrapper():
    """ A wrapper with proxies for properties.

    :param base: The wrapped object
    """

    def __init__(self, base) -> None:
        self._base: Any = base

    def __getattr__(self, attr) -> Any:
        return getattr(self._base, attr)
