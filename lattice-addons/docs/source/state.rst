State Management Library
========================

Prerequisites
-------------

- ``lattice-addons`` is installed

Usage
-----

The ``StateManagerGroup`` is a manager residing in the backend to help you manage states. To use the ``StateManagerGroup``, first register your states as shown below. The ``register`` function will register a slot in the ``StateManagerGroup`` with the corresponding key ``state1``. You will use this key to update and get your state.

.. code-block:: python

   from lattice_addons import StateManagerGroup

   mgr = StateManagerGroup()
   mgr.register('state1')

The next step is to update the registered slot with a state. The ``update`` function will keep a strong reference to the state object ``PicklableDict`` in the ``StateManagerGroup``. Once your program exits, the registered state will be automatically saved to a checkpoint according to the checkpoint settings (See ``LATTICE_CHECKPOINT_TYPE`` and ``LATTICE_CHECKPOINT_CONFIG`` in :ref:`patch:Patch settings`).

.. code-block:: python

   from lattice_addons import StateManagerGroup, PicklableDict

   mgr = StateManagerGroup()
   mgr.register('state1')

   state = PicklableDict(k1=3)
   mgr.update('state1', state)

There are other ways to associate your states, for example, a copy of the state objects:

.. code-block:: python

   from lattice_addons import StateManagerGroup, PicklableDict, StateCopyManager

   mgr = StateManagerGroup()
   mgr.register('state1', StateCopyManager)

   state = PicklableDict(k1=3)
   mgr.update('state1', state)


After the same program restarts, the ``StateManagerGroup`` will automatically discover and load the saved checkpoints for registered states. You can use the ``get`` function to fetch the latest states from a checkpoint.

.. code-block:: python

   from lattice_addons import StateManagerGroup, PicklableDict, StateCopyManager

   mgr = StateManagerGroup()
   mgr.register('state1', StateCopyManager)

   if mgr.get('state1') is not None:
      state = mgr.get()


Special Cases
-------------

Certain objects such as simple float or int values do not use references and therefore cannot be automatically updated with
the default state manager.
To track the state of objects like ``int`` or ``float``, you can use either ``StateClosureManager`` or ``StateSymbolicManager``.
To use ``StateClosureManager`` for example, use the ``update()`` function in the following way:

.. code-block:: python

   from lattice_addons import StateManagerGroup, StateClosureManager

   mgr = StateManagerGroup()
   mgr.register('loss', StateClosureManager)

   loss = 0.1
   mgr.update('loss', lambda: loss)

   loss = 0.2

For built-in types such as int or float, you can also use the ``StateSymbolicManager``. As the name implies, this will
track the value of a variable using its name.

.. code-block:: python

   from lattice_addons import StateManagerGroup, StateSymbolicManager

   mgr = StateManagerGroup()
   mgr.register('loss', StateSymbolicManager)

   loss = 0.1
   mgr.update('loss', loss)

   loss = 0.2

In both cases, this will return the most up to date loss value.
Upon restart, make sure to call ``mgr.get('loss')`` to get the most up to date loss value.


You can also save the state of files using the StateManager. For example:

.. code-block:: python

   from lattice_addons import StateManagerGroup

   mgr = StateManagerGroup()
   mgr.register('file')

   f = open('test.txt', 'w')
   mgr.update('file', f)

   f.write('hello')

When the program is restarted, calling ``mgr.get('file')`` will return a file with all contents
identical to the previous run, as well as the position in the file.
In this case, the file would contain the content ``hello``.




API reference
-------------

.. automodule:: lattice_addons

.. automodule:: lattice_addons.state
   :members:
   :imported-members:
   :undoc-members:
   :show-inheritance:
