from .constants import ADHOC_ATTRIBUTE_KEY
from lattice_addons.log import get_logger
from lattice_addons.state import StateManagerGroup, StateClosureManager, PicklableWrapper
from typing import Any, Dict, cast

import transformers
import os

_logger = get_logger(__name__)


def wrap_trainer_init(__init__, self: transformers.Trainer, args, kwargs) -> Any:

    retval = __init__(*args, **kwargs)

    mgr = StateManagerGroup()
    key = mgr.keygen(self)
    mgr.register(key, StateClosureManager)

    state = mgr.get(key)
    if state is not None:
        state = cast(PicklableWrapper, state)   # For mypy only

        _logger.debug(f"Load step {state.wrapped['global_step']} checkpoint")

        checkpoint_path = os.path.join(self._get_output_dir(None), f"checkpoint-{state.wrapped['global_step']}")
        recreate_checkpoint(checkpoint_path, state.wrapped['file_dict'])
        self.args.resume_from_checkpoint = checkpoint_path
        self.args.overwrite_output_dir = False

    def getter() -> PicklableWrapper:
        global_step = self.state.global_step

        _logger.debug(f"Save a checkpoint after step {global_step}")

        self._save_checkpoint(None, None, None)
        checkpoint_path = os.path.join(self._get_output_dir(None), f"checkpoint-{global_step}")
        file_dict = read_and_delete_checkpoint(checkpoint_path)

        return PicklableWrapper({'global_step': global_step,
                                 'file_dict': file_dict})

    mgr.update(key, getter)

    # Record key as an ad-hoc attribute, as we may need to use it for
    # saving states
    setattr(self, ADHOC_ATTRIBUTE_KEY, key)

    return retval


def read_and_delete_checkpoint(folder_path: str) -> Dict[str, bytes]:
    file_dict = {}

    # Read binary files and store them in the dictionary
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                file_dict[file] = f.read()
            os.remove(file_path)  # Delete the file

    os.rmdir(folder_path)   # Delete the folder
    return file_dict


def recreate_checkpoint(folder_path: str, file_dict: Dict[str, bytes]) -> None:
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)  # Create the folder if it doesn't exist

    for file, content in file_dict.items():
        file_path = os.path.join(folder_path, file)
        with open(file_path, "wb") as f:
            f.write(content)
