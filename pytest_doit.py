import os
import sys
import ast
import StringIO

from doit import loader
from doit.dependency import Dependency
from doit.cmds import doit_run


############# find imports using AST

def _file2ast(file_name):
    """get ast-tree from file_name"""
    fp = open(file_name, 'r')
    text = fp.read()
    fp.close()
    return ast.parse(text, file_name)

class _ImportsFinder(ast.NodeVisitor):
    """find all imports
    @ivar imports: (list - tuple) (module, name, asname, level)
    """
    def __init__(self):
        ast.NodeVisitor.__init__(self)
        self.imports = []

    def visit_Import(self, node):
        """callback for 'import' statement"""
        self.imports.extend((None, n.name, n.asname, None)
                            for n in node.names)
        ast.NodeVisitor.generic_visit(self, node)

    def visit_ImportFrom(self, node):
        """callback for 'import from' statement"""
        self.imports.extend((node.module, n.name, n.asname, node.level)
                            for n in node.names)
        ast.NodeVisitor.generic_visit(self, node)

def find_imports(file_path):
    """get list of import from python module
    @return: (list - tuple) (module, name, asname, level)
    """
    mod_ast = _file2ast(file_path)
    finder = _ImportsFinder()
    finder.visit(mod_ast)
    return finder.imports


############## process module imports

class _PyModule(object):
    """Represents a python module. Can find imported modules
    """
    def __init__(self, module_set, path, top=None):
        """
        @param module_set (ModuleSet)
        """
        self.module_set = module_set
        self.path = path
        self.name = self.path2name(path)
        self.imports = None # list of module names
        self.pkg = self.is_pkg(path)
        self.top = top or self.get_top_namespace(path)

    @staticmethod
    def is_pkg(path):
        return (os.path.isdir(path) and
                os.path.exists(os.path.join(path, '__init__.py')))

    @classmethod
    def get_top_namespace(cls, path):
        """get top package or module name"""
        print "n:", path
        current_path = os.path.basename(path)
        if current_path.endswith('.py'):
            current_path = current_path[:-3]
        parent_path = os.path.dirname(path)
        while True:
            print "-> %s + %s" % (parent_path, current_path)
            if not cls.is_pkg(parent_path):
                return current_path
            current_path = os.path.basename(parent_path)
            parent_path = os.path.dirname(current_path)

    @staticmethod
    def path2name(path):
        """convert file path to module dot-separated module name"""
        assert path.endswith('.py')
        return path[:-3].replace('/', '.')

    def _add_import(self, module):
        """add another module as import
        @param module: (_PyModule)
        """
        self.imports.add(module.path)

    def set_imports(self):
        """set imports from module
        must be called after all PyModule objects have been created
        """
        self.imports = set()
        raw_imports = find_imports(self.path)
        for x in raw_imports:
            # join 'from' and 'import' part of import statement
            full = ".".join(s for s in x[:2] if s is not None)

            # TODO: if levels

            # get first part of import and remove imports to external modules
            first = full.split('.')[0]
            if first not in self.module_set.top:
                continue

            # if imported module on module_set add to list
            imp_mod = self.module_set.modules.get(full)
            if imp_mod:
                self._add_import(imp_mod)
                continue

            # last part of import section might not be a module
            # remove last section
            only = full.rsplit('.', 1)[0]
            imp_mod2 = self.module_set.modules.get(only)
            if imp_mod2:
                self._add_import(imp_mod2)
                continue

            # special case for __init__
            if full in self.module_set.pkgs:
                pkg_name = full  + ".__init__"
                self._add_import(self.module_set.modules[pkg_name])
                continue

            if only in self.module_set.pkgs:
                pkg_name = only +  ".__init__"
                self._add_import(self.module_set.modules[pkg_name])
                continue

            assert False


class ModuleSet(object):
    """helper to filter import list only from within packages"""
    def __init__(self, path_list):
        # top packages/modules to match imports
        self.top = set()
        self.pkgs = set()
        self.modules = {} # key by path

        for path in path_list:
            # create modules object
            mod = _PyModule(self, path)
            # get top package/module
            self.top.add(mod.top)
            if mod.name.endswith('.__init__'):
                self.pkgs.add(mod.name[:-9]) # 9 == len('.__init__')
            self.modules[mod.name] = mod


    def by_path(self, path):
        name = _PyModule.path2name(path)
        return self.modules.get(name, None)


######### start doit section

def get_dep(module_path):
    mod = PY_MODS.by_path(module_path)
    mod.set_imports()
    return {'file_dep': [dep for dep in mod.imports if dep in PY_FILES]}
def task_get_dep():
    """get direct dependencies for each module"""
    for mod in PY_FILES:
        yield {'name': mod,
               'actions':[(get_dep,[mod])],
               'file_dep': [mod],
               }

def get_acc_dep(mod, dependencies):
    """get direct and indirect dependencies"""
    acc = ["acc_dep:%s" %m for m in dependencies]
    return {'calc_dep': acc,
            'file_dep': list(dependencies)}
def task_acc_dep():
    for mod in PY_FILES:
        yield {'name': mod,
               'actions': [(get_acc_dep, [mod])],
               'file_dep': [mod],
               'calc_dep': ["get_dep:%s" % mod],
               }

class OutdatedReporter(object):
    """A doit reporter"""
    def __init__(self, outstream, options):
        self.outdated = []
        self.outstream = outstream
    def get_status(self, task):
        pass
    def execute_task(self, task):
        if task.name.startswith('outdated:'):
            self.outdated.append(task.name.split(':',1)[1])
    def add_failure(self, task, exception):
        pass
    def add_success(self, task):
        pass
    def skip_uptodate(self, task):
        pass
    def skip_ignore(self, task):
        pass
    def cleanup_error(self, exception):
        pass
    def runtime_error(self, msg):
        pass
    def teardown_task(self, task):
        pass
    def complete_run(self):
        self.outstream.write("%r" % self.outdated)

def task_outdated():
    """find which tests are not up-to-date"""
    def fail():
        return False
    for test in TEST_FILES:
        yield {'name': test,
               'actions': [fail],
               'file_dep': [test],
               'calc_dep': ["acc_dep:%s" % test],
               'verbosity': 0}


# required to execute doit tasks without using py.test
DOIT_CONFIG = {'continue': True,
               'reporter': OutdatedReporter,
               }


TEST_FILES = []
PY_FILES = []
PY_MODS = []

def constants(py_files, test_files):
    global PY_MODS
    PY_FILES[:] = list(set(py_files + test_files))
    TEST_FILES[:] = test_files
    PY_MODS = ModuleSet(PY_FILES)


# for manual testing
#import glob
#constants(glob.glob("doit/*.py") + glob.glob("tests/*.py"),
#          glob.glob("tests/test_*.py")
#          )

##################### end doit section

import glob
import pytest

def pytest_addoption(parser):
    group = parser.getgroup("collect")
    group.addoption('--outdated', action="store_true", dest="outdated_only",
            default=False,
            help="execute only outdated tests (based on modified files)")
    group._addoption('--watch-pkg',
        action="append", dest="watch_pkg", default=[],
        help="(doit plugin) watch for file changes in these packages")

def pytest_configure(config):
    if config.option.outdated_only:
        config._doit = DoitOutdated()
        config.pluginmanager.register(config._doit)

def pytest_unconfigure(config):
    doit_plugin = getattr(config, '_doit', None)
    if doit_plugin:
        del config._doit
        config.pluginmanager.unregister(doit_plugin)


class DoitOutdated(object):
    """pytest-doit plugin class

    @cvar DB_FILE: (str) file name used as doit db file
    @ivar tasks: (dict) with reference to doit tasks
    @ivar py_files: (list - str) relative path of test and code under test
    @ivar success: (list - str) path of test files (of tests that succeed)
    @ivar fail: (list - str) path of test files (of tests that failed)
    @ivar uptodate: (list - pytest.Item) wont be executed
    @ivar pkg_folders

    how it works
    =============

    * pytest_sessionstart: check configuration
    * pytest_collect_file: to find out python files that doit will keep track
    * pytest_collection_modifyitems (get_outdated): run doit and remove
             up-to-date tests from test items
    * pytest_runloop: print info on terminal
    * pytest_runtest_makereport: collect result from individual tests
    * pytest_sessionfinish (set_success): save successful tasks in doit db
    """

    DB_FILE = '.pytest-doit'

    def __init__(self):
        self.tasks = None
        self.py_files = []
        self.success = set()
        self.fail = set()
        self.uptodate = None
        self.pkg_folders = None

    def get_outdated(self, test_files):
        """run doit to find out which test files are "outdated"
        A test file is outdated if there was a change in the content in any
        import (direct or indirect) since last succesful execution
        """
        constants(self.py_files, list(test_files))
        dodo = loader.load_task_generators(sys.modules[__name__])
        self.tasks = dict((t.name, t) for t in dodo['task_list'])
        output = StringIO.StringIO()
        doit_run(self.DB_FILE, dodo['task_list'], output, ['outdated'],
                 continue_=True, reporter=OutdatedReporter)
        output.seek(0)
        return output.read()


    def set_success(self, test_files):
        """mark doit test tasks as sucessful"""
        db = Dependency(self.DB_FILE)
        for path in test_files:
            #print "saving", path
            task_name = "outdated:%s" % path
            db.save_success(self.tasks[task_name])
        db.close()


    def pytest_sessionstart(self, session):
        self.pkg_folders = session.config.option.watch_pkg
        # TODO all tasks should depend on the value of PACKAGES
        if self.pkg_folders:
            for pkg in self.pkg_folders:
                # FIXME this must be recursive to find sub-packages
                pkg_glob = os.path.join(pkg, "*.py")
                self.py_files.extend(glob.glob(pkg_glob))
            return
        if not (len(session.config.args) == 1 and
                session.config.args[0] == os.getcwd()):
            msg = ("(plugin-doit) You are required to setup --watch-pkg"
                   " in order to use the plugin together with -k.")
            raise pytest.UsageError(msg)


    def pytest_collect_file(self, path, parent):
        """collect python files"""
        if (not self.pkg_folders) and path.strpath.endswith('.py'):
            self.py_files.append(os.path.relpath(path.strpath))


    def pytest_collection_modifyitems(self, session, config, items):
        """filter out up-to-date tests"""
        test_files = set((i.location[0] for i in items))
        outdated = set(eval(self.get_outdated(test_files)))
        selected = []
        deselected = []
        for colitem in items:
            path = colitem.location[0]
            if path in outdated:
                selected.append(colitem)
            else:
                deselected.append(colitem)
        items[:] = selected
        self.uptodate = deselected


    # FIXME should use termial to print stuff
    def pytest_runtestloop(self):
        """print info on up-to-date tests"""
        uptodate_test_files = set((item.location[0] for item in self.uptodate))
        if uptodate_test_files:
            print
        for test_file in sorted(uptodate_test_files):
            print "%s  [up-to-date]" % test_file


    def pytest_runtest_makereport(self, item, call):
        """save success and failures result so we can decide which files
        should be marked as successful in doit
        """
        if call.when == 'call':
            failures = getattr(call, 'result', None)
            # successful: call.result == []
            # skipped, xfail: call doesnt have result attribute
            if not failures:
                self.success.add(item.location[0])
            else:
                self.fail.add(item.location[0])


    def pytest_sessionfinish(self, session):
        """save success in doit"""
        # FIXME: need to check if all test were executed
        # in case -k is used. by now just consider not all were executed.
        if not getattr(session.config.option, 'keyword', None):
            self.set_success(list(self.success - self.fail))
