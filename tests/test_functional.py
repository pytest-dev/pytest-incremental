import sys
import time

pytest_plugins = 'pytester', 'incremental'


def get_results(recorder):
    '''filter records to get only call results'''
    results = {}
    for result in recorder.getreports():
        when = getattr(result, 'when', None)
        if  when is None:
            continue
        test_name = result.nodeid.split('::')[1]
        results[test_name, when] = result.outcome
    return results


TEST_FAIL = """
def foo():
    return 'foo'
def test_foo():
    assert 'bar' == foo()
"""

def test_fail_always_reexecute_test(testdir):
    test = testdir.makepyfile(TEST_FAIL)
    args = ['-v', '--inc', '--inc-path=%s'%test.dirpath(), test]

    # first time failed
    rec = testdir.inline_run(*args)
    results = get_results(rec)
    assert results['test_foo', 'call'] == 'failed'

    # second time re-executed
    rec2 = testdir.inline_run(*args)
    results2 = get_results(rec2)
    assert results2['test_foo', 'call'] == 'failed'


TEST_OK =  """
def foo():
    return 'foo'
def test_foo():
    assert 'foo' == foo()
"""

TEST_OK_2 =  """
def foo():
    return 'foo'
def test_foo():
    assert 'foo' == foo()
def test_bar():
    assert True
"""


def test_ok_reexecute_only_if_changed(testdir):
    # first time
    test = testdir.makepyfile(TEST_OK)
    args = ['-v', '--inc', '--inc-path=%s'%test.dirpath(), str(test)]

    # first time passed
    rec = testdir.inline_run(*args)
    results = get_results(rec)
    assert results['test_foo', 'call'] == 'passed'
    assert len(results) == 3

    # second time not executed because up-to-date
    rec2 = testdir.inline_run(*args)
    results2 = get_results(rec2)
    assert len(results2) == 0

    # change module
    del sys.modules['test_ok_reexecute_only_if_changed']
    test.write(TEST_OK_2)
    # re-execute tests
    rec3 = testdir.inline_run(*args)
    results3 = get_results(rec3)
    print(rec3.getreports(), results3)
    assert results3['test_foo', 'call'] == 'passed'
    assert results3['test_bar', 'call'] == 'passed'
    assert len(results3) == 6


TEST_SKIP =  """
import pytest

@pytest.mark.skipif("True")
def test_my_skip():
    assert False # not executed

@pytest.mark.xfail
def test_my_fail():
    assert False
"""


def test_skip_same_behaviour_as_passed(testdir):
    # first time
    test = testdir.makepyfile(TEST_SKIP)
    args = ['-v', '--inc', '--inc-path=%s'%test.dirpath(), test]

    rec = testdir.inline_run(*args)
    results = get_results(rec)
    assert results['test_my_skip', 'setup'] == 'skipped'
    assert results['test_my_fail', 'call'] == 'skipped'

    # second time not executed because up-to-date
    rec2 = testdir.inline_run(*args)
    results2 = get_results(rec2)
    assert len(results2) == 0
