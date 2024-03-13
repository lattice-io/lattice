.. lattice-addons documentation master file, created by
   sphinx-quickstart on Fri Dec 16 09:20:57 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. role:: primary

Lattice Addons
==============

Lattice Addons are extensions for popular ML frameworks providing necessary functionalities for fault tolerance without any code modification. After you installed the Lattice Addons, your machine learning stateful jobs will automatically save their states into checkpoints to handle interruptions, such as :primary:`spot instance preemption` and :primary:`auto-scaling events`.

Features
--------

Enjoy the following features out of the box:

**🔮 Zero-code change**

Lattice Addons will help you :primary:`automatically save and load checkpoints` for stateful Python objects, such as ``Module``, ``Optimizer``, and ``DataLoader`` for PyTorch training jobs without any code change. It also supports inherited objects, like a customized ``DataLoader``.

**🔬 Sub-epoch checkpoints**

Lattice Addons can capture and resume the most recent state updates, which means your training job can be recovered from the exact training step when it is interrupted, or in other words, :primary:`step-level checkpoints`.

**🕹️ Configurable checkpoint strategies**

Lattice Addons are flexible enough for different checkpoint strategies, such as :primary:`"at exit" checkpoint` for zero overhead, or :primary:`periodic checkpoint` with varying frequencies, depending on your performance and reliability requirements for different jobs.

**🚀 Minimize checkpoint overhead**

Lattice Addons apply various IO optimizations for checkpoint saving and loading, which achieves less than :primary:`5% overhead` for periodic checkpoint on our benchmark models, with a 100x improvement compared with the baseline.

**💾 Multiple checkpoint backends**

Lattice Addons support multiple checkpoint storage options, either locally such as a local file system, or remotely like a TCP-based store or S3.

**📦 Extensible state management**

Lattice Addons can also be used to manually save and load any customized Python objects that you think will have influence on your training progress.

Use Cases
---------

Lattice Addons can be used in following ways:

1. **Framework patches** are non-intrusive and transparent solutions to let existing ML frameworks handle elastic scaling events. It will dynamically modify the behaviors of core objects in a target framework, such as ``Module`` and ``DataLoader`` in PyTorch, and make them automatically save their states before exit and resume their states after restarting using checkpoints. Simply install the ``lattice-addons`` PyPi package is everything you need to do.

2. **State management libraries** serve advanced users whose codebase contains customized stateful objects, which does not exist in ML frameworks. The library provides unified and easy-to-use interfaces to preserve states for these objects. It can work seamlessly with framework patches.

.. NOTE: Include installation section after we release the wheel packages
.. Installation
.. ------------

Contents
--------

.. toctree::


   Home <self>
   patch
   state
