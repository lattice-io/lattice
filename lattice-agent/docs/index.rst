Lattice Agent
=============

Use the Lattice Agent as a framework agnostic replacement for the torchelastic agent.
Useful for running any kind of batch jobs in a dynamic cluster where nodes can
leave and join the cluster over time (or any case where auto-scaling is possible).

Features
--------

The main purpose of the agent is to dynamically find other workers when it is unkown
beforehand how many workers we will be able to schedule. The agent will dynamically
rendezvous with other agents that have been launched to correctly configure any
distributed environment.

In addition, when failures are encountered, for example a node leaves and its worker
is shutdown, the agent will detect the failure and re-rendezvous to create a new
distributed configuration with the new set of workers.

All logic fro restarting the application must be handled at the application level, such
as saving and loading checkpoints in PyTorch.

Contents
--------

.. toctree::

   modules
