from .module import wrap_trainer_init
from lattice_addons.log import get_logger
from lattice_addons.patch import (
    patch_methods,
    patch_methods_for_subclasses,
    patch_methods_for_new_subclasses
)
from typing import Any

import transformers

logger = get_logger(__name__)


def patch(module: Any) -> None:
    logger.info('transformers patches applied')

    patch_module()


def patch_module() -> None:
    patch_methods(transformers, 'Trainer', {'__init__': wrap_trainer_init})
    patch_methods_for_subclasses(transformers, 'Trainer', {'__init__': wrap_trainer_init})
    patch_methods_for_new_subclasses(transformers, 'Trainer', {'__init__': wrap_trainer_init})
