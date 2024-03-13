# Lattice Installer

Goal of this package is to create a general installer for Lattice packages.
Specifically, a single entry point that can determine things like the python
version and any other relevant system configuration so that things like
the lattice-addons and lattice-agent are installed properly.

## Install

1. Run the following command to build the wheel:

```bash
python setup.py bdist_wheel
```

2. Install the package using pip:

```bash
pip install dist/lattice_installer-*.whl
```

## Usage

1. Set the following environment variables:

```bash
export LATTICE_JFROG_USER=<jfrog_username>
export LATTICE_JFROG_KEY=<jfrog_apikey>
```

2. Run the installer:

```bash
python -m lattice_installer.install
```

## Packages Installed

The following packages will be installed:
- lattice-agent
- lattice-addons-torch