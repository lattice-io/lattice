# Lattice Agent

## Build and Release

1. Create an entry in your `~/.pypirc` file that looks like the following:
```bash
[distutils]
index-servers = local

[local]
repository: https://breezeml.jfrog.io/artifactory/api/pypi/breezeml-pypi
username: <USERNAME>
password: <PASSWORD>
```
+ Make sure you have a JFrog account set up with BreezeML in order to upload

2. Run the following command:
```bash
python setup.py bdist_wheel upload -r local
```

## Install
Before you get started, please consult release adminitrators for your repo username and password.

To install, use the following
```bash
pip install --trusted-host breezeml.jrog.io/artifactory/api/pypi/breezeml-pypi/simple -i 'https://<username>:<password>@breezeml.jfrog.io/artifactory/api/pypi/breezeml-pypi/simple' lattice-addons-pytorch
```


## Running the Agent
Basic usage:

```shell
python -m lattice.torch.run python YOUR_TRAINING_SCRIPT.py
```

### Configure agent using arguments

The first way to pass arguments to the agent is to pass them directly to the training script, for example:
```
python -m lattice.torch.run --nnodes 1:8 --nproc_per_node 1 --rdzv_backend etcd python YOUR_TRAINING_SCRIPT.py
```

The arguments include:

```
nnodes:                     (required) Number of nodes, or the range of nodes in form <min_nodes>:<max_nodes>
framework:                  (not required; default='generic') The framework to use. If not provided, make as few assumptions about this job as possible.
nproc_per_node:             (not required; default=1) Number of workers per node

rdzv_backend:               (not required; default=etcd) Backend used for rendezvous (currently only supports etcd)
rdzv_client_service_host:   (not required; default=lattice-rdzv-client.lattice) Rendezvous backend endpoint
rdzv_client_service_port:   (not required; default=2379) Rendezvous backend port
rdzv_id:                    (required) User-defined identifier for this job
rdzv_conf:                  (not required; default="") Additional rendezvous configurations in form (<key1>=<val1>,<key2>=<val2>,...)

entrypoint:                 (required) Your application
entrypoint_args:            (requirement depends on entrypoint) Args to the applciation
```

+ Warning ⚠️: The `framework` is argument is used to decide which distributed environment
    to configure for the workers, for example setting `TF_CONFIG` for TensorFlow workers.
    If it is not set the agent will not configure the workers environment with any variables.


### Configure agent using environments variables

The second way is to pass the args to the training script through environment variables.
For every arg listed above, the corresponding environment variable to set it can be found
by using the following rule: The argument name is capitalized and preceded by "LATTICE_".
For example: `nnodes = LATTICE_NNODES`.

Therefore, you can use the following example to run the agent and set all its arguments:

```
LATTICE_NNODES=1:8                          \
LATTICE_FRAMEWORK=pytorch                   \
LATTICE_NPROC_PER_NODE=1                    \
LATTICE_RDZV_CLIENT_SERVICE_HOST=localhost  \
LATTICE_RDZV_CLIENT_SERVICE_PORT=2379       \
LATTICE_RDZV_BACKEND=etcd                   \
LATTICE_RDZV_ID=test-id                     \
python -m lattice.torch.run python YOUR_TRAINING_SCRIPT.py
```

## Development
For development, you should make sure you have the following dependencies installed:
+ `requirements/common.txt`: Required for agent to run
+ `requirements/dev.txt` Requirements for testing (linting and docs coming soon)
+ `etcd`: For running a local rendezvous server

You should also make sure to set your PYTHONPATH environment variable to
include the `lattice-agent/src` directory.

### Testing
For testing you can either run with the Dockerfile or locally.
If running locally, make sure you have all the above dependencies installed.
If running in the docker, just run `docker build . -t lattice-agent` to have
then setup for you.
Once the dependencies are installed, run `pytest tests` from the root directory.

## Documentation
**Local docs:**
This project uses Sphinx to generate documentation. To build the doc in html:
```bash
cd docs && make clean html
```

If you have added any new modules to the project that require docs, make sure to
add them using the `sphinx-apidocs` command.

To document your code, the docstring must follow the [Sphinx format](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html).
