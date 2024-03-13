Framework Patches
=================

Prerequisites
-------------

- ``lattice-addons`` is installed

Patch settings
--------------

Frameworks patches are controlled by a few environment variables:

.. list-table::
  :widths: 30 70
  :header-rows: 1

  * - Env variable
    - Description
  * - ``LATTICE_AUTOPATCH``
    - Target frameworks to patch
  * - ``LATTICE_LOGLEVEL``
    - Log level. Defaults to ``WARNING``
  * - ``LATTICE_CHECKPOINT_TYPE``
    - Checkpoint type
  * - ``LATTICE_CHECKPOINT_CONFIG``
    - Checkpoint config in comma-separated key value pairs


Currently supported patch targets:

.. list-table::
  :widths: 50 50
  :header-rows: 1

  * - Framework
    - Patch target value
  * - PyTorch
    - ``torch``
  * - Huggingface
    - ``transformers``

Huggingface patch has not yet been tested for compatibility with elasticity and 
it is not guaranteed to perform correctly when the job size is changed.

Currently supported checkpoints and their configurations:

.. list-table::
  :widths: 20 20 69
  :header-rows: 1

  * - Checkpoint type
    - Checkpoint type value
    - Checkpoint configuration options
  * - Common Checkpoint Configuration
    -
    - | ``atexit_saving``: Write checkpoint on failure. Options: `enabled` and `disabled`. Defaults to `enabled`
      | ``periodic_saving``: Write checkpoints during training. Options: `enabled` and `disabled`. Defaults to `disabled`
      | ``periodic_saving_interval``: How frequently to write checkpoints when periodic_saving is enabled
  * - Local file system
    - ``local``
    - ``root``: Root path for checkpoint files
  * - TCP checkpoint store
    - ``remote``
    - | ``job_id``: The ID of the job
      | ``ckpt_service_endpoint``: IP address of the checkpoint service
      | ``ckpt_service_port``: Port used by the checkpoint service
  * - S3
    - ``s3``
    - | ``root``: Where to look for checkpoints. Example: `s3://bucket-name/job-id/`


For example, if you want to start a PyTorch application using the directory ``/tmp/ckpt`` as the checkpoint root:

.. code-block:: bash

  export LATTICE_AUTOPATCH='torch'
  export LATTICE_CHECKPOINT_TYPE='local'
  export LATTICE_CHECKPOINT_CONFIG='root=/tmp/ckpt'
  python ...


.. warning::
    please use ``SIGTERM`` instead of ``SIGKILL`` to give the patched objects a grace period to save the states safely.
