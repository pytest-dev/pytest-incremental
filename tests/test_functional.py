import os
import sys

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


TEST_SAMPLE = """
def test_foo():
    assert True
def test_bar():
    assert True
"""


def test_list_deps(testdir, capsys):
    test = testdir.makepyfile(TEST_SAMPLE)
    args = ['--inc-deps', test]
    testdir.inline_run(*args)
    out = capsys.readouterr()[0].splitlines()
    assert ' - test_list_deps.py: test_list_deps.py' in out


def test_list_outdated(testdir, capsys):
    test = testdir.makepyfile(TEST_SAMPLE)
    args = ['--inc-outdated', test]
    testdir.inline_run(*args)
    out = list(reversed(capsys.readouterr()[0].splitlines()))
    while(out):
        line = out.pop()
        if line == 'List of outdated test files:':
            outdated_list = out.pop()
            assert 'test_list_outdated.py' in outdated_list
            break
    else:  # pragma: no cover
        assert False, 'outdated list not found'


def test_list_outdated_none(testdir, capsys):
    test = testdir.makepyfile(TEST_SAMPLE)
    testdir.inline_run('--inc', test)  # run so tests are not outdated
    testdir.inline_run('--inc-outdated', test)
    out = capsys.readouterr()[0].splitlines()
    assert 'All test files are up to date' in out


def test_graph(testdir, capsys):
    test = testdir.makepyfile(TEST_SAMPLE)
    args = ['-v', '--inc-graph', test]
    testdir.inline_run(*args)
    out = capsys.readouterr()[0].splitlines()
    assert 'Graph file written in deps.dot' in out


def test_fail_always_reexecute_test(testdir):
    TEST_FAIL = """
def foo():
    return 'foo'
def test_foo():
    assert 'bar' == foo()
"""

    test = testdir.makepyfile(TEST_FAIL)
    args = ['--inc', test]

    # first time failed
    rec = testdir.inline_run(*args)
    results = get_results(rec)
    assert results['test_foo', 'call'] == 'failed'

    # second time re-executed
    rec2 = testdir.inline_run(*args)
    results2 = get_results(rec2)
    assert results2['test_foo', 'call'] == 'failed'



def test_ok_reexecute_only_if_changed(testdir):
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
    # first time
    test = testdir.makepyfile(TEST_OK)
    args = ['--inc', str(test)]

    # first time passed
    rec = testdir.inline_run(*args)
    results = get_results(rec)
    assert results['test_foo', 'call'] == 'passed'
    assert len(results) == 3

    # second time not executed because up-to-date
    rec2 = testdir.inline_run(*args)
    results2 = get_results(rec2)
    assert len(results2) == 0

    # TODO remove when py.test 2.8 is released
    if 'test_ok_reexecute_only_if_changed' in sys.modules: # pragma: no cover
        del sys.modules['test_ok_reexecute_only_if_changed']

    # change module
    test.write(TEST_OK_2)
    # re-execute tests
    rec3 = testdir.inline_run(*args)
    results3 = get_results(rec3)
    print(rec3.getreports(), results3)
    assert results3['test_foo', 'call'] == 'passed'
    assert results3['test_bar', 'call'] == 'passed'
    assert len(results3) == 6




def test_skip_same_behaviour_as_passed(testdir):
    TEST_SKIP =  """
import pytest

@pytest.mark.skipif("True")
def test_my_skip():
    assert False # not executed

@pytest.mark.xfail
def test_my_fail():
    assert False
"""
    # first time
    test = testdir.makepyfile(TEST_SKIP)
    args = ['--inc', test]

    rec = testdir.inline_run(*args)
    results = get_results(rec)
    assert results['test_my_skip', 'setup'] == 'skipped'
    assert results['test_my_fail', 'call'] == 'skipped'

    # second time not executed because up-to-date
    rec2 = testdir.inline_run(*args)
    results2 = get_results(rec2)
    assert len(results2) == 0


def test_keyword_dont_save_success(testdir, capsys):
    test = testdir.makepyfile(TEST_SAMPLE)
    testdir.inline_run('--inc', '-k', 'foo', test)
    out = capsys.readouterr()[0].splitlines()
    assert 'WARNING: incremental not saving results because -k was used' in out

    rec = testdir.inline_run('--inc', test)
    results = get_results(rec)
    assert results['test_foo', 'call'] == 'passed'
    assert results['test_bar', 'call'] == 'passed'


def test_xdist_not_supported(testdir, capsys):
    from _pytest.main import EXIT_USAGEERROR
    test = testdir.makepyfile(TEST_SAMPLE)
    got = testdir.inline_run('--inc', '-n', '2', test)
    assert got.ret == EXIT_USAGEERROR
    err = capsys.readouterr()[1].splitlines()
    msg = 'ERROR: Plugin incremental is not compatible with plugin xdist.'
    assert msg in err


def test_inc_path(testdir, capsys):
    sub = testdir.mkdir('sub')
    base = os.path.relpath(str(sub)) # pass a relative path
    with open('sub/test_x.py', 'w') as fp:
        fp.write(TEST_SAMPLE)
    args = ['-v', '--inc', '--inc-path', base, base]
    testdir.inline_run(*args)
    out = capsys.readouterr()[0].splitlines()
    assert 'sub/test_x.py::test_foo PASSED' in out
