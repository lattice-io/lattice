# Welcome to Lattice Addons setup.py
#
#
# Environment variables you are probably interested in:
#
# 	LATTICE_COMPILE
# 		whether you should compile the source files in the wheel to `.pyc` files
# 		1 means compile
#

import os
import setuptools
from pathlib import Path
from dataclasses import dataclass, field
from pyc_wheel import convert_wheel
from typing import List, Dict


@dataclass
class FrameworkConfig:
    group: str
    module: str
    hook: str
    patch_name: str
    patch_path: str = ""
    dependencies: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.patch_path == "":
            self.patch_path = f'src/{self.patch_name}'


# Register the configurations for frameworks
registered_cfg = {
    'torch': FrameworkConfig(**{  # type: ignore[arg-type]
        'group': 'lattice_addons.autopatch_torch',
        'module': 'torch',
        'hook': 'lattice_autopatch_torch.hooks:patch',
        'patch_name': 'lattice_autopatch_torch',
        'dependencies': [
            line.strip()
            for line in open('requirements/torch.txt', 'r').readlines()
        ]
    }),
    'transformers': FrameworkConfig(**{  # type: ignore[arg-type]
        'group': 'lattice_addons.autopatch_transformers',
        'module': 'transformers',
        'hook': 'lattice_autopatch_transformers.hooks:patch',
        'patch_name': 'lattice_autopatch_transformers',
        'dependencies': [
            line.strip()
            for line in open('requirements/transformers.txt', 'r').readlines()
        ]
    })
}


# Choose auto-patch for frameworks
frameworks = [
    'torch',
    'transformers'
]


def get_entrypoints() -> Dict[str, List[str]]:
    groups = {
        cfg.group: [f'{cfg.module} = {cfg.hook}']
        for cfg in [registered_cfg.get(f, None) for f in frameworks] if cfg
    }

    return groups


def get_package_dir() -> Dict[str, str]:
    package_dir = {
        'lattice_autopatch': 'src/lattice_autopatch',
        'lattice_addons': 'src/lattice_addons',
        'lattice_addons.state': 'src/lattice_addons/state',
        'lattice_addons.state.distributed': 'src/lattice_addons/state/distributed',
        'lattice_addons.log': 'src/lattice_addons/log',
        'lattice_addons.patch': 'src/lattice_addons/patch'
    }
    extra_package_dir = {
        cfg.patch_name: cfg.patch_path
        for cfg in [registered_cfg.get(f, None) for f in frameworks] if cfg
    }
    package_dir = {**package_dir, **extra_package_dir}

    return package_dir


def get_packages() -> List[str]:
    package_dir = get_package_dir()

    packages = list(package_dir.keys())
    return packages


def get_install_requires() -> List[str]:
    install_requires = []
    with open("requirements/common.txt", "r") as f:
        install_requires += [line.strip() for line in f.readlines()]

    return install_requires


def get_optional_dependencies() -> Dict[str, List[str]]:
    optional_dependencies = {
        framework: registered_cfg[framework].dependencies
        for framework in registered_cfg.keys()
    }

    return optional_dependencies


def get_version() -> str:
    root = Path(__file__).parent
    return open(root / "version", "r").read().strip()


def get_package_data() -> Dict[str, List[str]]:
    pth_hooks = {'lattice_autopatch': ['../lattice_autopatch.pth']}

    return pth_hooks


setuptools.setup(
    name="lattice_addons",
    version=get_version(),
    description="Lattice Add-ons",
    package_dir=get_package_dir(),
    packages=get_packages(),
    entry_points=get_entrypoints(),
    python_requires=">=3.7",
    install_requires=get_install_requires(),
    include_package_data=True,
    package_data=get_package_data(),
    extras_require=get_optional_dependencies(),
)


if os.getenv('LATTICE_COMPILE', '0') == '1':
    convert_wheel(
        Path(f'dist/lattice_addons-{get_version()}-py3-none-any.whl')
    )
