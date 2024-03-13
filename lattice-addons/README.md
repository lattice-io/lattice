# Lattice Addons

## Installation

The current version only supports "build from source" as it replies on the `get_python_lib` to statically write locations for data files.

### Build from source

Prerequisites:

- Python 3.7 or later
- Ensure pip, setuptools, and wheel are installed
- (Optional) Install pyc_wheel for compilation

Run the following command to create a wheel package under the directory `./dist/`:

```bash
python setup.py bdist_wheel
```

If you want to create a version of the package with only bytecode (all `.py` files
replaced by `.pyc` files), run `setup.py` with the environment variable
`LATTICE_COMPILE` set to `1`.

And then install the wheel package.

## Usage

See [Documentation](#documentation)

## Development

Currently, this project does not support development mode. You have to build and install the wheel package.

For development, you should install a few dependencies:

- `requirements/common.txt`: Must-have requirements.
- `requirements/dev.txt`: Development-only requirements, including dependencies for testing, linting, and documentation
- `requirements/<framework>.txt`: Framework-specific requirements.

Before you run any section here, you should also set `PYTHONPATH` to include the directory `src/`.

### Linting

This project uses `mypy` to check typing issues. All function parameters and returns should be explicitly typed to enable `mypy`, even if it takes nothing and return nothing. For some `mypy` errors you can use `type: ignore[<mypy-error>]` to ignore them, but try to explain why this should be ignored.

This project uses `flake8` to check format issues. The configuration for `flake8` is stored in `.flake8`.

### Testing

This project uses `pytest` for testing. It also replies [`pytest-fork`](https://github.com/pytest-dev/pytest-forked), in order to let each test function run in separated subprocess. To run all tests under a directory, first make sure you set `PYTHONPATH` include `src` directory, and then run:

```bash
pytest --forked <test-directory>
```

### Documentation

**Online docs**:

https://lattice-addons.docs.breezeml.ai/ (Password: `zwt8fkz-nyk*ZFY3eym`).

**Local docs**:

This project uses Sphinx to generate documentation. To build the doc in html:

```bash
cd docs && make html
```

This will generate html files in `docs/build/html/`.

To document your code, the docstring must follow [Sphinx format](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)

## Deployment

### Documentation Site

The documentation site is deployed on Netlify.

Prerequisites:

- [Netlify CLI](https://docs.netlify.com/cli/get-started/)
- Set the env var `NETLIFY_SITE_ID` to be the site id (`60192f2c-93e0-4f50-aec9-40c73b3e5325`)
- Set the env var `NETLIFY_AUTH_TOKEN` to be your netlify API access token

Run the following command to deploy:

```bash
netlify deploy --dir docs/build/html/ --auth $NETLIFY_AUTH_TOKEN --site ${NETLIFY_SITE_ID}
```

To deploy to production, add the flag `--prod`.

## Troubleshooting

### Auto-patching in automatic mode

Auto-patching in automatic mode is based ["Automatic Post-import Monkey Patching"](https://github.com/GrahamDumpleton/wrapt/blob/develop/blog/14-automatic-patching-of-python-applications.md). It starts with a executable `.pth` (`src/lattice_autopatch.pth`) which will be placed in your current Python site-packages directory after installing the wheel package. The relative path of the site-packages directory is hard-coded in the wheel package when build the project using the function `get_python_lib(prefix="")`.

To make sure the `.pth` file is installed in the correct location, get the absolute path of your current site-packages directory:

```bash
python -c 'from distutils.sysconfig import get_python_lib; print(get_python_lib())'
```

The file `lattice_autopatch.pth` should be placed there.
