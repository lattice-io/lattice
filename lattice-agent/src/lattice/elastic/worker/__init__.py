from lattice.elastic.worker.constants import (
    NO_FRAMEWORK,
    PYTORCH_JOB_FRAMEWORK,
    PYTORCH_LIGHTNING_JOB_FRAMEWORK,
    TENSORFLOW_JOB_FRAMEWORK
)
from lattice.elastic.worker.api import (
    get_generic_worker_info,
    get_pytorch_worker_info,
    get_pytorch_lightning_worker_info,
    get_tensorflow_worker_info,
    create_generic_worker,
    create_pytorch_workers,
    create_pytorch_lightning_workers,
    create_tensorflow_workers,
    worker_registry
)

worker_registry.register_info_gatherer(NO_FRAMEWORK, get_generic_worker_info)
worker_registry.register_worker_creator(NO_FRAMEWORK, create_generic_worker)

worker_registry.register_info_gatherer(PYTORCH_JOB_FRAMEWORK, get_pytorch_worker_info)
worker_registry.register_worker_creator(PYTORCH_JOB_FRAMEWORK, create_pytorch_workers)

worker_registry.register_info_gatherer(PYTORCH_LIGHTNING_JOB_FRAMEWORK, get_pytorch_lightning_worker_info)
worker_registry.register_worker_creator(PYTORCH_LIGHTNING_JOB_FRAMEWORK, create_pytorch_lightning_workers)

worker_registry.register_info_gatherer(TENSORFLOW_JOB_FRAMEWORK, get_tensorflow_worker_info)
worker_registry.register_worker_creator(TENSORFLOW_JOB_FRAMEWORK, create_tensorflow_workers)
