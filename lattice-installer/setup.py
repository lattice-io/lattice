import setuptools


def get_version() -> str:
    return open("version", "r").readline().strip()


setuptools.setup(
    name="lattice-installer",
    version=get_version(),
    description="Lattice Installer",
    packages=setuptools.find_packages(where="src"),
    package_dir={"lattice_installer": "src/lattice_installer"},
    python_requires=">=3.7"
)
