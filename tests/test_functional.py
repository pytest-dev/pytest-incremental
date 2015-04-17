import time

pytest_plugins = 'pytester', 'incremental'


TEST_FAIL = """
def foo():
    return 'foo'
def test_foo():
    assert 'bar' == foo()
"""

def test_fail_always_reexecute_test(testdir):
    test = testdir.makepyfile(TEST_FAIL)
    result = testdir.runpytest('-v', '--incremental',
                               '--watch-path=%s'%test.dirpath(), test)
    result.stdout.fnmatch_lines([
            '*test_foo FAILED',
            ])
    result2 = testdir.runpytest('-v', '--incremental',
                                '--watch-path=%s'%test.dirpath(), test)
    result2.stdout.fnmatch_lines([
            '*test_foo FAILED',
            ])


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
    assert True
"""


def test_ok_reexecute_only_if_changed(testdir):
    # first time
    test = testdir.makepyfile(TEST_OK)
    result = testdir.runpytest('-v', '--incremental',
                               '--watch-path=%s'%test.dirpath(), test)
    result.stdout.fnmatch_lines(['*test_foo PASSED'])

    # second time not executed because up-to-date
    result2 = testdir.runpytest('-v', '--incremental',
                                '--watch-path=%s'%test.dirpath(), test)
    result2.stdout.fnmatch_lines(['*up-to-date*'])

    # sleep for a while to make sure modified content
    # wont have the same timestamp
    time.sleep(0.5)

    # change file, re-execute tests
    test2 = testdir.makepyfile(TEST_OK_2)
    result = testdir.runpytest('-v', '--incremental',
                               '--watch-path=%s'%test.dirpath(), test2)
    result.stdout.fnmatch_lines(['*test_foo PASSED'])


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
    result = testdir.runpytest('-v', '--incremental',
                               '--watch-path=%s'%test.dirpath(), test)
    result.stdout.fnmatch_lines([
            '*test_my_skip SKIPPED',
            '*test_my_fail xfail',
            ])

    # second time not executed because up-to-date
    result2 = testdir.runpytest('-v', '--incremental',
                                '--watch-path=%s'%test.dirpath(), test)
    result2.stdout.fnmatch_lines([
            '*up-to-date*',
            ])
