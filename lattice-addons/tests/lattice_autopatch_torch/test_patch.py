from lattice_addons.patch import (
    patch_methods,
    patch_methods_for_subclasses,
    patch_methods_for_new_subclasses
)
from typing import Any
import pytest

import torch


def test_patch_methods():
    mod = torch.nn.Module()
    with pytest.raises(Exception):
        getattr(mod, 'patch')

    def wrapper(wrapped, instance, args, kwargs):
        retval = wrapped(*args, **kwargs)
        setattr(instance, 'patch', 1)
        return retval

    patch_methods('torch', 'nn.Module', {'__init__': wrapper})

    mod = torch.nn.Module()
    assert getattr(mod, 'patch') == 1


def test_patch_methods_for_subclasses():
    mod = torch.nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2)
    with pytest.raises(Exception):
        getattr(mod, 'patch')

    def wrapper(wrapped, instance, args, kwargs):
        retval = wrapped(*args, **kwargs)

        # NOTE: a chile class may use super(), which also gives a wrapped
        # function. So we need to keep these nested cases.
        if not hasattr(instance, 'patch'):
            setattr(instance, 'patch', 1)

        return retval

    patch_methods_for_subclasses('torch', 'nn.Module', {'__init__': wrapper})

    mod = torch.nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2)
    assert getattr(mod, 'patch') == 1


def test_patch_methods_for_new_subclasses():
    class MyModule1(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = torch.nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2)

        def forward(self, x: Any) -> Any:
            return self.conv1(x)

    mod = MyModule1()
    with pytest.raises(Exception):
        getattr(mod, 'patch')

    def wrapper(wrapped, instance, args, kwargs):
        retval = wrapped(*args, **kwargs)
        if not hasattr(instance, 'patch'):
            setattr(instance, 'patch', 1)
        return retval

    patch_methods_for_new_subclasses('torch', 'nn.Module', {'__init__': wrapper})

    class MyModule2(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = torch.nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2)

        def forward(self, x: Any) -> Any:
            return self.conv1(x)

    mod = MyModule2()
    assert getattr(mod, 'patch') == 1


def test_patch_methods_for_all():
    def wrapper(wrapped, instance, args, kwargs):
        retval = wrapped(*args, **kwargs)
        if not hasattr(instance, 'patch'):
            setattr(instance, 'patch', 1)
        return retval

    patch_methods('torch', 'nn.Module', {'__init__': wrapper})
    patch_methods_for_subclasses('torch', 'nn.Module', {'__init__': wrapper})
    patch_methods_for_new_subclasses('torch', 'nn.Module', {'__init__': wrapper})

    mod = torch.nn.Module()
    assert getattr(mod, 'patch') == 1

    mod = torch.nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2)
    assert getattr(mod, 'patch') == 1

    class MyModule(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = torch.nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2)

        def forward(self, x: Any) -> Any:
            return self.conv1(x)

    mod = MyModule()
    assert getattr(mod, 'patch') == 1
