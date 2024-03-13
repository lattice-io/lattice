from lattice_addons.state import (
    State, PicklableDict,
    StateManager, StateCopyManager, StateRefManager, StateClosureManager, StateManagerGroup,
    StateSymbolicManager,
    CHECKPOINT_TYPE, CHECKPOINT_CONFIG
)

import os
import sys
import tempfile
import pytest
import copy
import atexit
import multiprocessing as mp
from typing import Tuple
import random
import time


def test_simple_state_mgr():
    mgr = StateManager(uid='state_mgr')
    assert mgr.get() is None

    state = PicklableDict(k1=3)
    mgr.update(state)

    state["k2"] = 4
    assert "k2" in mgr.get()


def test_file_checkpoint():
    test_file_name = '_test_file.txt'
    st_mode = 33279

    def scope():
        f = open(test_file_name, 'w')

        mgr = StateManager(uid='file_checkpoint_mgr')
        mgr.update(f)

        f.write('hello')
        os.chmod(test_file_name, st_mode)

        mgr.save()

        f.close()
        os.remove(test_file_name)

    def scope2():
        mgr = StateManager(uid='file_checkpoint_mgr')

        mgr.load()

        f = mgr.get()

        f.write(' world!')
        f.close()

    scope()
    scope2()

    with open(test_file_name, 'r') as f:
        assert f.read() == 'hello world!'
        assert os.fstat(f.fileno()).st_mode == st_mode

    os.remove(test_file_name)


def test_immutable_types_with_closure():
    def get_random_loss():
        return random.uniform(0.0, 10.0)

    def run(prev_loss=None):
        mgr = StateClosureManager(uid='closure_manager')
        mgr.load()

        loss = mgr.get()
        if loss is None:
            loss = 0.0
        elif loss is not None and prev_loss is not None:
            assert loss == prev_loss

        mgr.update(lambda: loss)
        loss = get_random_loss()

        assert mgr.get() == loss

        mgr.save()

        return loss

    prev_loss = run()
    run(prev_loss)


def test_immutable_types_with_inspect():
    def get_random_loss():
        return random.uniform(0.0, 10.0)

    def run(prev_loss=None):
        mgr = StateSymbolicManager(uid='closure_manager')
        mgr.load()

        loss = mgr.get()
        if loss is None:
            loss = 0.0
        elif loss is not None and prev_loss is not None:
            assert loss == prev_loss

        mgr.update(loss)
        loss = get_random_loss()

        assert mgr.get() == loss

        mgr.save()

        return loss

    prev_loss = run()
    run(prev_loss)


def test_cached_state_mgr():
    def scope() -> None:
        mgr = StateManager(uid='state_mgr')

        state = PicklableDict(k1=3)
        mgr.update(state)

    scope()
    mgr = StateManager(uid='state_mgr')
    assert mgr.get() is not None


def test_delete_in_state_mgr():
    mgr = StateManager(uid='state_mgr')

    state = PicklableDict(k1=3)
    mgr.update(state)

    assert sys.getrefcount(state) == 3
    mgr.delete()

    assert mgr.get() is None
    assert sys.getrefcount(state) == 2


def test_multi_state_mgr():
    mgr = StateManager(uid='state_mgr')
    mgr2 = StateManager(uid='state_mgr')
    mgr3 = StateManager(uid='state_mgr_x')
    assert mgr is mgr2
    assert mgr is not mgr3


def test_ckpt_for_state_mgr():
    def scope1() -> State:
        mgr = StateManager(uid='state_mgr')

        # No ckpt found
        mgr.load()
        assert mgr.get() is None

        state = PicklableDict(k1=3)
        mgr.update(state)
        mgr.save()
        mgr.delete()

        assert mgr.get() is None
        return copy.deepcopy(state)

    def scope2(state) -> None:
        mgr = StateManager(uid='state_mgr')

        assert mgr.get() is None

        mgr.load()

        assert mgr.get() == state

    state = scope1()
    scope2(state)


def test_state_copy_mgr():
    mgr = StateCopyManager(uid='state_copy_mgr')
    assert mgr.get() is None

    state = PicklableDict(k1=3)
    mgr.update(state)

    state["k2"] = 4
    assert "k2" not in mgr.get()


def test_state_ref_mgr():
    def scope() -> None:
        mgr = StateRefManager(uid='state_ref_mgr')
        assert mgr.get() is None

        state = PicklableDict(k1=3)
        mgr.update(state)

        state["k2"] = 4
        assert "k2" in mgr.get()

    scope()
    mgr = StateRefManager(uid='state_ref_mgr')

    # state is deleted, so weak reference gives None
    assert mgr.get() is None


def test_state_closure_mgr():
    def scope() -> State:
        mgr = StateClosureManager(uid='state_cls_mgr')

        state = PicklableDict(k1=3)

        def get_state():
            return state
        mgr.update(get_state)

        return copy.deepcopy(state)

    state = scope()
    mgr = StateClosureManager(uid='state_cls_mgr')

    assert state == mgr.get()


def test_ckpt_for_state_ref_mgr():
    def scope1() -> None:
        mgr = StateRefManager(uid='state_ref_mgr')

        state = PicklableDict(k1=3)
        mgr.update(state)
        mgr.save()

    def scope2() -> None:
        mgr = StateRefManager(uid='state_ref_mgr')

        # state is garbage collected
        assert mgr.get() is None

        # state is still owned by mgr
        mgr.load()

    def scope3() -> None:
        mgr = StateRefManager(uid='state_ref_mgr')

        # state only lives in this scope
        state = mgr.get()
        assert state is not None

    def scope4() -> None:
        mgr = StateRefManager(uid='state_ref_mgr')

        # state is garbage collected
        assert mgr.get() is None

    scope1()
    scope2()
    scope3()
    scope4()


def test_state_mgr_group():
    def scope1() -> Tuple[State, State]:
        mgr = StateManagerGroup()

        mgr.register('state1')

        # Conflict key
        with pytest.raises(KeyError):
            mgr.register('state1')

        mgr.register('state2')

        # Dummy save
        mgr.save()

        assert mgr.get('state1') is None
        assert mgr.get('state2') is None

        state1 = PicklableDict(k1=3)
        state2 = PicklableDict(k2=4)
        mgr.update('state1', state1)
        mgr.update('state2', state2)
        mgr.save()

        mgr.delete('*')
        return (copy.deepcopy(state1), copy.deepcopy(state2))

    def scope2(state1, state2) -> None:
        mgr = StateManagerGroup()

        assert not mgr.contain('state1')
        assert not mgr.contain('state2')

        mgr.register('state1')
        mgr.register('state2')

        # Auto load

        assert mgr.get('state1') == state1
        assert mgr.get('state2') == state2

    s1, s2 = scope1()
    scope2(s1, s2)


def test_autosave_state_mgr_group1():
    root = tempfile.mkdtemp()
    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = f'root={root}'

    def fn1():
        mgr = StateManagerGroup()

        state = PicklableDict(k1=3)
        mgr.register('state')
        mgr.update('state', state)

        # TODO(p0):: When os._exit() is called, the atexit handler is not called.
        # os._exit() is used in the child process after a fork(). We must force
        # to clean here
        atexit._run_exitfuncs()

    def fn2():
        mgr = StateManagerGroup()

        mgr.register('state')
        assert mgr.get('state') is not None

    p = mp.Process(target=fn1)
    p.start()
    p.join()
    assert p.exitcode == 0

    p = mp.Process(target=fn2)
    p.start()
    p.join()
    assert p.exitcode == 0


def test_autosave_state_mgr_group2():
    root = tempfile.mkdtemp()
    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = f'root={root}'

    def fn1():
        _ = StateManagerGroup()

        # TODO(p0):: When os._exit() is called, the atexit handler is not called.
        # os._exit() is used in the child process after a fork(). We must force
        # to clean here
        atexit._run_exitfuncs()

    def fn2():
        mgr = StateManagerGroup()

        mgr.register('state')
        assert mgr.get('state') is None

    p = mp.Process(target=fn1)
    p.start()
    p.join()
    assert p.exitcode == 0

    p = mp.Process(target=fn2)
    p.start()
    p.join()
    assert p.exitcode == 0


def test_keygen_in_state_mgr_group():
    mgr = StateManagerGroup()

    state1 = PicklableDict(k1=3)
    state2 = PicklableDict(k2=4)

    key1 = mgr.keygen(state1)
    key2 = mgr.keygen(state2)

    assert key1 != key2


def test_priodic_saving():
    root = tempfile.mkdtemp()
    os.environ[CHECKPOINT_TYPE] = 'local'
    os.environ[CHECKPOINT_CONFIG] = (f'root={root},'
                                     'atexit_saving=disabled,'
                                     'periodic_saving=enabled,'
                                     'periodic_saving_interval=0.05')

    def fn1():
        mgr = StateManagerGroup()
        mgr.register('state1', StateManager)
        state = PicklableDict(k1=3)
        mgr.update('state1', state)
        state["k2"] = 4
        time.sleep(0.1)

    def fn2():
        mgr = StateManagerGroup()
        mgr.register('state1', StateManager)

        state = mgr.get('state1')
        assert state["k1"] == 3
        assert state["k2"] == 4

    p = mp.Process(target=fn1)
    p.start()
    p.join()

    fn2()
