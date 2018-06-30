import os

from six import StringIO
import py
import pytest
from doit.cmd_run import Run
from doit.cmd_base import DodoTaskLoader

from pytest_incremental import IncrementalTasks
from pytest_incremental import IncrementalControl, OutdatedReporter


#### fixture for "doit.db". create/remove for every test
# (copied from doit/tests/conftest.py)
def remove_db(filename):
    """remove db file from anydbm"""
    # dbm on some systems add '.db' on others add ('.dir', '.pag')
    extensions = ['', #dbhash #gdbm
                  '.bak', #dumbdb
                  '.dat', #dumbdb
                  '.dir', #dumbdb #dbm2
                  '.db', #dbm1
                  '.pag', #dbm2
                  ]
    for ext in extensions:
        if os.path.exists(filename + ext):
            os.remove(filename + ext)

@pytest.fixture
def depfile_name(request):
    # copied from tempdir plugin
    name = request._pyfuncitem.name
    name = py.std.re.sub(r"[\W]", "_", name)
    my_tmpdir = request.config._tmpdirhandler.mktemp(name, numbered=True)
    depfile_name = (os.path.join(my_tmpdir.strpath, "testdb"))

    def remove_depfile():
        remove_db(depfile_name)
    request.addfinalizer(remove_depfile)

    return depfile_name
##########################################

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), 'sample-inc')

@pytest.fixture
def cmd_run(request, depfile_name):
    output = StringIO()
    cmd = Run(task_loader=DodoTaskLoader())
    params, _ = cmd.cmdparser.parse([])
    params['outfile'] = output
    params['dodoFile'] = os.path.join(SAMPLE_DIR, 'dodo.py')
    params['cwdPath'] = SAMPLE_DIR
    params['dep_file'] = depfile_name
    cmd.params = params  # hack to make params available from fixture
    return cmd

@pytest.fixture
def rm_generated_deps(request):
    """remove deps.* files generated from running tasks on sample-inc folder"""
    def remove():
        for path in ('deps.json', 'deps.dot', 'deps.svg'):
            try:
                os.remove(os.path.join(SAMPLE_DIR, path))
            except OSError:
                pass
    request.addfinalizer(remove)


class TestTasks(object):
    def test_print_deps(self, cmd_run, rm_generated_deps, capsys):
        # all deps in all levels
        cmd_run.execute(cmd_run.params, ['print-deps'])
        got = cmd_run.outstream.getvalue().splitlines()
        # FIXME there is some bad interaction of doit and py.test
        # leaving the output from tasks directly into stdout but not on
        # specified outstream
        out = capsys.readouterr()[0].splitlines()
        assert '.  dep-json' in got
        assert ' - mod2.py: mod1.py, mod2.py' in out
        mod2_deps = 'mod1.py, mod2.py, tt/conftest.py, tt/tt_mod2.py'
        assert ' - tt/tt_mod2.py: ' + mod2_deps in out

    def test_dot_graph(self, cmd_run, rm_generated_deps):
        cmd_run.execute(cmd_run.params, ['dep-dot'])
        got = cmd_run.outstream.getvalue().splitlines()
        assert '.  dep-dot' in got
        dot = open(os.path.join(SAMPLE_DIR, 'deps.dot')).read()
        got = dot.splitlines()
        assert '''"mod1.py"''' in got
        assert '''"mod2.py" -> "mod1.py"''' in got
        assert '''"tt/tt_mod1.py" -> "mod1.py"''' in got
        assert '''"tt/tt_mod2.py" -> "mod2.py"''' in got

    def test_img_graph(self, cmd_run, rm_generated_deps):
        # dumb test just check task is created
        IncrementalTasks(['xxx'], ['yyy'])
        cmd_run.execute(cmd_run.params, ['dep-image'])
        got = cmd_run.outstream.getvalue().splitlines()
        assert '.  dep-image' in got



class FakeTask(object):
    def __init__(self, name):
        self.name = name
class TestOutdatedRerporter(object):
    def test_output(self):
        output = StringIO()
        rep = OutdatedReporter(output, None)
        rep.execute_task(FakeTask('foo'))
        rep.execute_task(FakeTask('outdated:xxx'))
        rep.execute_task(FakeTask('NOToutdated:abc'))
        rep.execute_task(FakeTask('outdated:yyy'))
        rep.complete_run()
        assert output.getvalue() == '["xxx", "yyy"]'

    def test_failure(self):
        output = StringIO()
        rep = OutdatedReporter(output, None)
        # failures of outdated tasks are expected, so nothing happens
        rep.add_failure(FakeTask('outdated:xxx'), Exception())
        # failures on any other task raise error
        pytest.raises(pytest.UsageError, rep.add_failure,
                      FakeTask('x'), Exception())

    def test_runtime_error(self):
        output = StringIO()
        rep = OutdatedReporter(output, None)
        pytest.raises(Exception, rep.runtime_error, 'error msg')


class TestIncrementalControl(object):
    tt_conf = os.path.join(SAMPLE_DIR, 'tt/conftest.py')
    tt_mod1 = os.path.join(SAMPLE_DIR, 'tt/tt_mod1.py')
    tt_mod2 = os.path.join(SAMPLE_DIR, 'tt/tt_mod2.py')
    def test_py_files(self):
        control = IncrementalControl([SAMPLE_DIR])
        assert len(control.py_files) == 6
        assert os.path.join(SAMPLE_DIR, 'mod1.py') in control.py_files
        assert os.path.join(SAMPLE_DIR, 'mod2.py') in control.py_files
        assert self.tt_conf in control.py_files
        assert self.tt_mod1 in control.py_files
        assert self.tt_mod2 in control.py_files

    def test_outdated(self, depfile_name, rm_generated_deps):
        control = IncrementalControl([SAMPLE_DIR])
        control.DB_FILE = depfile_name
        control.test_files = [self.tt_mod1, self.tt_mod2]

        # at first all are outdated
        got = control.get_outdated()
        assert set(got.keys()) == set([self.tt_mod1, self.tt_mod2])

        # save one success and check outdated
        control.save_success([self.tt_mod2])
        assert set(control.get_outdated().keys()) == set([self.tt_mod1])


    def test_list_deps(self, depfile_name, rm_generated_deps, capsys):
        control = IncrementalControl([SAMPLE_DIR])
        control.DB_FILE = depfile_name
        control.test_files = [self.tt_mod1, self.tt_mod2]
        control.print_deps()
        out = capsys.readouterr()[0].splitlines()
        assert len(out) == 6
        assert ' - dodo.py: dodo.py' in out
        assert ' - mod1.py: mod1.py' in out
        assert ' - mod2.py: mod1.py, mod2.py' in out
        assert ' - tt/conftest.py: tt/conftest.py' in out
        assert ' - tt/tt_mod1.py: mod1.py, tt/conftest.py, tt/tt_mod1.py' in out
        mod2_deps = 'mod1.py, mod2.py, tt/conftest.py, tt/tt_mod2.py'
        assert ' - tt/tt_mod2.py: ' + mod2_deps in out

    def test_dot_graph(self, depfile_name, rm_generated_deps):
        control = IncrementalControl([SAMPLE_DIR])
        control.DB_FILE = depfile_name
        control.test_files = [self.tt_mod1, self.tt_mod2]
        control.create_dot_graph()
        dot = open(os.path.join(SAMPLE_DIR, 'deps.dot')).read()
        out = dot.splitlines()
        assert len(out) == 9
        assert 'rankdir = BT' in out
        assert '"dodo.py"' in out
        assert '"mod1.py"' in out
        assert '"mod2.py" -> "mod1.py"' in out
        assert '"tt/conftest.py"' in out
        assert '"tt/tt_mod1.py" -> "mod1.py"' in out
        assert '"tt/tt_mod2.py" -> "mod2.py"' in out

