from packaging.requirements import Requirement
from packaging.version import parse
from lattice_addons.log import get_logger

import pkg_resources
import os
import site

logger = get_logger(__name__)

_registered = False
_patched = False

AUTOPATCH_ENV = "LATTICE_AUTOPATCH"

REQUIREMENTS = [
    'torch>=1.10.0,<=1.13.1',
    'transformers>=4.27.0,<=4.29.2'
]


def register_bootstrap_functions():
    '''Discover and register all post import hooks named in the
    'AUTOWRAPT_BOOTSTRAP' environment variable. The value of the
    environment variable must be a comma separated list.

    '''

    # This can be called twice if '.pth' file bootstrapping works and
    # the 'autowrapt' wrapper script is still also used. We therefore
    # protect ourselves just in case it is called a second time as we
    # only want to force registration once.

    global _registered

    if _registered:
        return

    _registered = True

    # if /tmp/autopatching exists, read the frameworks to patch from
    # this file and put them into the AUTOPATCH_ENV
    autopatching_file_path = "/tmp/autopatching"
    autopatching_file_exists = os.path.exists(autopatching_file_path)

    if autopatching_file_exists:
        with open(autopatching_file_path, 'r') as file:
            autopatching_frameworks = [line.strip() for line in file]
        if autopatching_frameworks:
            os.environ[AUTOPATCH_ENV] = ','.join(autopatching_frameworks)

    # validate packages
    packages_to_check = os.environ.get(AUTOPATCH_ENV, '').split(',')
    valid_packages = _get_valid_packages(REQUIREMENTS, packages_to_check)

    # don't patch both torch and transformers, they have conflicts
    # TODO: create a final validation function to check patching conflicts
    # between libraries
    if 'torch' in valid_packages and 'transformers' in valid_packages:
        valid_packages.remove('torch')
        logger.info("Addons will not be enabled for 'torch'.")

    # It should be safe to import wrapt at this point as this code will
    # be executed after all Python module search directories have been
    # added to the module search path.

    from wrapt import discover_post_import_hooks

    for name in valid_packages:
        discover_post_import_hooks(f'lattice_addons.autopatch_{name}')


def _get_installed_version(package):
    try:
        return pkg_resources.get_distribution(package).version
    except pkg_resources.DistributionNotFound:
        return None


def _is_valid_version(installed_version, required_version):
    if not required_version:  # if the SpecifierSet is empty
        return True
    return parse(installed_version) in required_version


def _get_valid_packages(all_requirements, packages_to_check):
    valid_packages = []

    requirements_dict = {}
    for r in all_requirements:
        requirement = Requirement(r)
        requirements_dict[requirement.name] = requirement.specifier

    for package in packages_to_check:
        if package not in requirements_dict:
            logger.info(f"{package} is not in the list of supported frameworks.")
            continue

        installed_version = _get_installed_version(package)

        if installed_version is None:
            logger.info(f"{package} is not installed. Addons will not be enabled for {package}.")
            continue

        if _is_valid_version(installed_version, requirements_dict[package]):
            valid_packages.append(package)
        else:
            logger.info(
                f"{package} has an invalid version. Installed version: {installed_version}, "
                f"valid range: {requirements_dict[package]}.\n"
                f"Addons will not be enabled for {package}."
            )
    return valid_packages


def _execsitecustomize_wrapper(wrapped):
    def _execsitecustomize(*args, **kwargs):
        try:
            return wrapped(*args, **kwargs)
        finally:
            # Check whether 'usercustomize' module support is disabled.
            # In the case of 'usercustomize' module support being
            # disabled we must instead do our work here after the
            # 'sitecustomize' module has been loaded.

            if not site.ENABLE_USER_SITE:
                register_bootstrap_functions()

    return _execsitecustomize


def _execusercustomize_wrapper(wrapped):
    def _execusercustomize(*args, **kwargs):
        try:
            return wrapped(*args, **kwargs)
        finally:
            register_bootstrap_functions()

    return _execusercustomize


def bootstrap():
    '''Patches the 'site' module such that the bootstrap functions for
    registering the post import hook callback functions are called as
    the last thing done when initialising the Python interpreter. This
    function would normally be called from the special '.pth' file.

    '''

    global _patched

    if _patched:
        return

    _patched = True

    # We want to do our real work as the very last thing in the 'site'
    # module when it is being imported so that the module search path is
    # initialised properly. What is the last thing executed depends on
    # whether the 'usercustomize' module support is enabled. Support for
    # the 'usercustomize' module will not be enabled in Python virtual
    # enviromments. We therefore wrap the functions for the loading of
    # both the 'sitecustomize' and 'usercustomize' modules but detect
    # when 'usercustomize' support is disabled and in that case do what
    # we need to after the 'sitecustomize' module is loaded.
    #
    # In wrapping these functions though, we can't actually use wrapt to
    # do so. This is because depending on how wrapt was installed it may
    # technically be dependent on '.pth' evaluation for Python to know
    # where to import it from. The addition of the directory which
    # contains wrapt may not yet have been done. We thus use a simple
    # function wrapper instead.

    site.execsitecustomize = _execsitecustomize_wrapper(site.execsitecustomize)
    site.execusercustomize = _execusercustomize_wrapper(site.execusercustomize)
