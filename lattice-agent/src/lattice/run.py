from argparse import REMAINDER, ArgumentParser
import GPUtil
import logging
import os
from typing import Callable, List, Tuple, Union

from lattice.elastic.rendezvous.utils import _parse_rendezvous_config
from lattice.launcher.api import LaunchConfig, elastic_launch

from argparse import Action


class env(Action):
    def __init__(self, dest, default=None, required=False, **kwargs) -> None:
        env_name = f"LATTICE_{dest.upper()}"
        default = os.environ.get(env_name, default)

        # ``required`` means that it NEEDS to be present  in the command-line args
        # rather than "this option requires a value (either set explicitly or default"
        # so if we found default then we don't "require" it to be in the command-line
        # so set it to False
        if default:
            required = False

        super().__init__(dest=dest, default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def get_args_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Lattice Agent Launcher")

    # Worker/node size related arguments
    parser.add_argument(
        "--framework",
        action=env,
        help="The ML framework that is being used for the workers",
        default='generic'
    )
    parser.add_argument(
        "--nnodes",
        action=env,
        help="Number of nodes, or the range of nodes in form <minimum_nodes>:<maximum_nodes>",
        required=True,
    )
    parser.add_argument(
        "--nproc_per_node",
        action=env,
        default=1,
        help="Number of workers per node"
    )

    # Rendezvous related arguments
    parser.add_argument(
        "--rdzv_backend",
        action=env,
        default='etcd',
        help="Backend used for rendezvous"
    )
    parser.add_argument(
        '--rdzv_client_service_host',
        action=env,
        default="lattice-rdzv-client.lattice",
        help="Rendezvous backend endpoint",
    )
    parser.add_argument(
        '--rdzv_client_service_port',
        action=env,
        default="2379",
        help="Rendezvous backend port"
    )
    parser.add_argument(
        "--rdzv_id",
        action=env,
        help="User-defined group id",
        required=True,
    )
    parser.add_argument(
        "--rdzv_conf",
        action=env,
        default="",
        help="Additional rendezvous configuration (<key1>=<value1>,<key2>=<value2>,...)",
    )
    parser.add_argument(
        "--metric_pushgateway_endpoint",
        action=env,
        default="prometheus-pushgateway.prometheus:9091",
        help="Metric pushgateway endpoint"
    )
    parser.add_argument(
        "--metric_pushgateway_backend",
        action=env,
        default="prometheus",
        help="Metric pushgateway backend"
    )

    # Positional arguments.
    parser.add_argument(
        "entrypoint",
        type=str,
        help="Command that the agent should run in the subprocess"
        "followed by all the arguments to the command.",
    )

    parser.add_argument("entrypoint_args", nargs=REMAINDER)

    return parser


def parse_args(args):
    parser = get_args_parser()
    return parser.parse_args(args)


def parse_min_max_nnodes(nnodes: str):
    arr = nnodes.split(":")

    if len(arr) == 1:
        min_nodes = max_nodes = int(arr[0])
    elif len(arr) == 2:
        min_nodes = int(arr[0])
        max_nodes = int(arr[1])
    else:
        raise RuntimeError(f'nnodes={nnodes} is not in "MIN:MAX" format')

    return min_nodes, max_nodes


def get_device_count():
    return len(GPUtil.getAvailable())


def gpus_available():
    return get_device_count() != 0


def determine_local_world_size(nproc_per_node: str):
    try:
        logging.info(f"Using nproc_per_node={nproc_per_node}.")
        return int(nproc_per_node)
    except ValueError:
        if nproc_per_node == "cpu":
            num_proc = os.cpu_count()
            device_type = "cpu"
        elif nproc_per_node == "gpu":
            if not gpus_available():
                raise ValueError("Cuda is not available.")
            device_type = "gpu"
            num_proc = get_device_count()
        elif nproc_per_node == "auto":
            if gpus_available():
                num_proc = get_device_count()
                device_type = "gpu"
            else:
                num_proc = os.cpu_count()
                device_type = "cpu"
        else:
            raise ValueError(f"Unsupported nproc_per_node value: {nproc_per_node}")

        logging.info(
            f"Using nproc_per_node={nproc_per_node},"
            f" seting to {num_proc} since the instance "
            f"has {os.cpu_count()} {device_type}"
        )
        return num_proc


def config_from_args(args) -> Tuple[LaunchConfig, Union[Callable, str], List[str]]:
    # If ``args`` not passed, defaults to ``sys.argv[:1]``
    min_nodes, max_nodes = parse_min_max_nnodes(args.nnodes)
    assert 0 < min_nodes <= max_nodes

    nproc_per_node = determine_local_world_size(args.nproc_per_node)
    if "OMP_NUM_THREADS" not in os.environ and nproc_per_node > 1:
        omp_num_threads = 1
        logging.warning(
            f"\n*****************************************\n"
            f"Setting OMP_NUM_THREADS environment variable for each process to be "
            f"{omp_num_threads} in default, to avoid your system being overloaded, "
            f"please further tune the variable for optimal performance in "
            f"your application as needed. \n"
            f"*****************************************"
        )
        # This env variable will be passed down to the subprocesses
        os.environ["OMP_NUM_THREADS"] = str(omp_num_threads)

    rdzv_configs = _parse_rendezvous_config(args.rdzv_conf)

    config = LaunchConfig(
        framework=args.framework,
        min_nodes=min_nodes,
        max_nodes=max_nodes,
        nproc_per_node=nproc_per_node,
        run_id=args.rdzv_id,
        rdzv_endpoint=args.rdzv_client_service_host,
        rdzv_port=args.rdzv_client_service_port,
        rdzv_backend=args.rdzv_backend,
        rdzv_configs=rdzv_configs,
        metric_pushgateway_endpoint=args.metric_pushgateway_endpoint,
        metric_pushgateway_backend=args.metric_pushgateway_backend
    )

    cmd: Union[Callable, str]
    cmd = args.entrypoint
    cmd_args = args.entrypoint_args

    return config, cmd, cmd_args


def run(args):
    config, cmd, cmd_args = config_from_args(args)
    elastic_launch(
        config=config,
        entrypoint=cmd,
    )(*cmd_args)


def main(args=None):
    args = parse_args(args)
    run(args)


if __name__ == "__main__":
    main()
