from .module import wrap_module_init
from .optimizer import wrap_optimizer_init
from .data import wrap_dataloader_init

from lattice_addons.log import get_logger
from lattice_addons.patch import (
    patch_methods,
    patch_methods_for_subclasses,
    patch_methods_for_new_subclasses
)

from typing import Any

logger = get_logger(__name__)


def patch(module: Any) -> None:
    logger.info('torch patches applied')

    patch_module(module)
    patch_optimizer(module)
    patch_dataloader(module)


def patch_module(torch: Any) -> None:
    patch_methods(torch, 'nn.Module', {'__init__': wrap_module_init})
    patch_methods_for_subclasses(torch, 'nn.Module', {'__init__': wrap_module_init})
    patch_methods_for_new_subclasses(torch, 'nn.Module', {'__init__': wrap_module_init})


def patch_optimizer(torch: Any) -> None:
    patch_methods(torch, 'optim.Optimizer', {'__init__': wrap_optimizer_init})
    patch_methods_for_subclasses(torch, 'optim.Optimizer', {'__init__': wrap_optimizer_init})
    patch_methods_for_new_subclasses(torch, 'optim.Optimizer', {'__init__': wrap_optimizer_init})


def patch_dataloader(torch: Any) -> None:
    patch_methods(torch, 'utils.data.DataLoader', {'__init__': wrap_dataloader_init})

    # NOTE: Do not patch subclasses of DataLoader, which is based on these assumptions:
    # 1. Most of users will not define their own derived DataLoader
    # 2. Even users define their own derived DataLoader, they will still always use the initialized fields in
    # the base DataLoader class.

    # patch_methods_for_subclasses(torch, 'utils.data.DataLoader', {'__init__': wrap_dataloader_init})
    # patch_methods_for_new_subclasses(torch, 'utils.data.DataLoader', {'__init__': wrap_dataloader_init})
