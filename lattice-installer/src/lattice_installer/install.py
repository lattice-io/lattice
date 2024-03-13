# This is an installer for lattice packages meant to run
# on a docker container right before an application starts.
# It assumes that the docker is running with python installed,
# however, it attempts to use only built in python packes to
# avoid making assumptions about a users environment.

import argparse
import os
import subprocess as sp
import sys
import importlib
import warnings

EXPECTED_TORCH_VERSION='1.10.0'

parser = argparse.ArgumentParser()
parser.add_argument('original_cmd', type=str)
parser.add_argument('--framework', type=str, required=False)

args = parser.parse_args()

packages = ["lattice-agent", "lattice-addons"]
frameworks = ["torch", "transformers"]
autopatching_file_path = "/tmp/autopatching"
jfrog_user = os.environ.get("LATTICE_JFROG_USER")
jfrog_key = os.environ.get("LATTICE_JFROG_KEY")
jfrog_url = f"https://{jfrog_user}:{jfrog_key}" \
            "@breezeml.jfrog.io/artifactory/api/pypi/breezeml-pypi/simple"


class InvalidEnvironmentException(Exception):
    def __init__(sefl, msg, *args, **kwargs):
        super.__init__(msg, args, kwargs)

def perform_environment_checks():
    original_command = args.original_cmd
    # TODO(p1): Perform some checks on the original command such as
    # what kind of command and whether we are able to support it

    # issue a warning message when a deprecated argument is used
    if args.framework is not None:
        warning_message = (
            "The argument '--framework' is deprecated and will be removed in "
            "future versions. Frameworks will be patched if they are installed."
        )
        warnings.warn(warning_message, DeprecationWarning)

    # Check python version
    ver = sys.version_info
    if not (ver.major >= 3 and ver.minor >= 7):
        raise InvalidEnvironmentException("python version must be >= python3.7")

    # Check if pip is installed
    return_code = sp.check_call(['pip', '--version'], stdout=sp.PIPE, stderr=sp.PIPE)
    if return_code != 0:
        raise InvalidEnvironmentException("pip is not installed. Run on a container with pip")


def install_packages():
    for package in packages:
        sp.run(['pip', 'install', package, '-i', jfrog_url])


def check_installed_packages(package_list):
    installed_packages = []

    for package in package_list:
        try:
            importlib.import_module(package)
            installed_packages.append(package)
        except ImportError:
            print(f"Package '{package}' not installed or available.")
            continue

    return installed_packages


def write_list_to_file(strings, filename):
    with open(filename, 'w') as file:
        for string in strings:
            file.write(f"{string}\n")


if __name__ == '__main__':

    perform_environment_checks()

    frameworks_to_patch = check_installed_packages(frameworks)
    write_list_to_file(frameworks_to_patch, autopatching_file_path)

    install_packages()
