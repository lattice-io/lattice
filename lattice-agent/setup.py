from pathlib import Path
import setuptools


def get_version() -> str:
    root = Path(__file__).parent
    return open(root / "version.txt", "r").read().strip()


__version__ = get_version()


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="lattice-agent",
    version=__version__,
    description="Lattice Agent",
    long_description=long_description,
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    python_requires=">=3.7",
    install_requires=[
        'GPUtil>=1.0',
        'python-etcd>=0.4',
        'requests>=2.0',
        'prometheus-client>=0.15.0',
        'kubernetes'
    ]
)
