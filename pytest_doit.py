import os
import sys
import ast
import StringIO

from doit import loader
from doit.dependency import Dependency
from doit.cmds import doit_run


############# find imports using AST

def file2ast(file_name):
    """get ast-tree from file_name"""
    fp = open(file_name, 'r')
    text = fp.read()
    fp.close()
    return ast.parse(text, file_name)

class ImportsFinder(ast.NodeVisitor):
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
    mod_ast = file2ast(file_path)
    finder = ImportsFinder()
    finder.visit(mod_ast)
    return finder.imports

############## process module imports

class _PyMod(object):
    def __init__(self, module_set, path):
        self._set = module_set
        self.path = path
        self.name = self.path2name(path)
        self.imports = None # list of module names
    @staticmethod
    def path2name(path):
        return path[:-3].replace('/', '.')
    def get_imports(self):
        """set imports from module
        must be called after all PyMod objects have been created
        """
        self.imports = set()
        raw_imports = find_imports(self.path)
        for x in raw_imports:
            # join 'from' and 'import' part of import statement
            full = ".".join(s for s in x[:2] if s is not None)

            # get top part of import and remove imports to external modules
            top = full.split('.')[0]
            if top not in self._set.packages:
                continue

            # last part of import section might not be a module
            imp_mod = self._set.modules.get(full)
            if imp_mod:
                self.imports.add(imp_mod.path)
                continue
            # remove last section
            only = full.rsplit('.', 1)[0]
            imp_mod = self._set.modules.get(only)
            if imp_mod:
                self.imports.add(imp_mod.path)
            elif only == top:
                self.imports.add(only + "/__init__.py")

class ModuleSet(object):
    """helper to filter import list only from within packages"""
    def __init__(self, packages, path_list):
        self.packages = packages # list of packages to collect imports
        self.modules = {} # key by path
        for path in path_list:
            mod = _PyMod(self, path)
            self.modules[mod.name] = mod

    def by_path(self, path):
        name = _PyMod.path2name(path)
        return self.modules.get(name, None)


######### start doit section

def get_dep(module_path):
    mod = PY_MODS.by_path(module_path)
    mod.get_imports()
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
PACKAGES = []
PY_MODS = []

def constants(py_files, test_files):
    global PY_MODS
    PY_FILES[:] = list(set(py_files + test_files))
    TEST_FILES[:] = test_files
    # TODO all tasks should depend on the value of PACKAGES
    PACKAGES[:] = (list(set((os.path.split(p)[0] for p in py_files))) +
                   list(set((os.path.split(p)[0] for p in test_files)))
                   )
    PY_MODS = ModuleSet(PACKAGES, PY_FILES)


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
        if self.pkg_folders:
            for pkg in self.pkg_folders:
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
            if getattr(call,'result',None) == []:
                # FIXME: need to check if all test were executed
                # in case -k is used
                self.success.add(item.location[0])
            else:
                self.fail.add(item.location[0])


    def pytest_sessionfinish(self, session):
        """save success in doit"""
        self.set_success(list(self.success - self.fail))
