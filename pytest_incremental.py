"""
pytest-incremental : an incremental test runner (pytest plugin)
https://bitbucket.org/schettino72/pytest-incremental

The MIT License - see LICENSE file
Copyright (c) 2011-2013 Eduardo Naufel Schettino
"""

__version__ = (0, 3, 0)

import os
import ast
import StringIO
import fcntl

from doit.dependency import Dependency
from doit.cmd_base import ModuleTaskLoader
from doit.cmd_run import Run
from doit.tools import result_dep

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
    def __init__(self, path):
        self.path = path
        self.name = self.get_namespace(path)
        self.imports = None # list of module names
        self.pkg = self.is_pkg(path)

    @staticmethod
    def is_pkg(path):
        return (os.path.isdir(path) and
                os.path.exists(os.path.join(path, '__init__.py')))

    @classmethod
    def get_namespace(cls, path):
        """get package or module full name
        @return list of names
        """
        name_list = []
        current_path = os.path.basename(path)
        if current_path.endswith('.py'):
            current_path = current_path[:-3]
        parent_path = os.path.dirname(path)
        while True:
            name_list.append(current_path)
            if not cls.is_pkg(parent_path):
                name_list.reverse()
                return name_list
            current_path = os.path.basename(parent_path)
            parent_path = os.path.dirname(parent_path)

    def add_import(self, module):
        """add another module as import
        @param module: (_PyModule)
        """
        self.imports.add(module.path)

    def __repr__(self): # pragma: no cover
        return "<_PyModule %s>" % self.path


class ModuleSet(object):
    """helper to filter import list only from within packages"""
    def __init__(self, path_list):
        self.pkgs = set()
        self.by_path = {} # module by path
        self.by_name = {} # module by name (dot separated)

        for path in path_list:
            # create modules object
            mod = _PyModule(path)
            if mod.name[-1] == '__init__':
                self.pkgs.add('.'.join(mod.name[:-1]))
            self.by_path[path] = mod
            self.by_name['.'.join(mod.name)] = mod


    def _get_imported_module(self, module_name):
        """try to get imported module reference by its name"""
        # if imported module on module_set add to list
        imp_mod = self.by_name.get(module_name)
        if imp_mod:
            return imp_mod

        # last part of import section might not be a module
        # remove last section
        only = module_name.rsplit('.', 1)[0]
        imp_mod2 = self.by_name.get(only)
        if imp_mod2:
            return imp_mod2

        # special case for __init__
        if module_name in self.pkgs:
            pkg_name = module_name  + ".__init__"
            return self.by_name[pkg_name]
        if only in self.pkgs:
            pkg_name = only +  ".__init__"
            return self.by_name[pkg_name]


    def set_imports(self, module):
        """set imports for module"""
        module.imports = set()
        raw_imports = find_imports(module.path)
        for import_entry in raw_imports:
            try_names = []
            # join 'from' and 'import' part of import statement
            full = ".".join(s for s in import_entry[:2] if s)

            import_level = import_entry[3]
            if import_level:
                # intra package imports
                intra = '.'.join(module.name[:-import_level] + [full])
                try_names = (intra,)
            else:
                # deal with old-style relative imports
                module_pkg = '.'.join(module.name[:-1])
                full_relative = "%s.%s" % (module_pkg, full)
                try_names = (full_relative, full,)

            for imported_name in try_names:
                imported = self._get_imported_module(imported_name)
                if imported:
                    module.add_import(imported)
                    break

            # didnt find... must be out of tracked namespaces


######### start doit section

class IncrementalTasks(object):
    """generate doit tasks used by pytest-incremental

    @ivar py_mods (ModuleSet)
    @ivar py_files (list - str): files being watched for changes
    """
    def __init__(self, py_files):
        self.py_files = py_files
        self.py_mods = ModuleSet(py_files)
        print "YYYYYYYYYYYY", self.py_files

    def gen_watched_files(self):
        """task to be used as a result_dep

        Result contains a list of modules with tests.

        This is required because list of imports per module will be filtered
        out based on this value.
        """
        yield {
            'basename': 'watched_files',
            'actions': [ (lambda fl: str(sorted(fl)), [self.py_files]) ]
            }


    def _get_dep(self, module_path):
        """action: return imports from module as file_dep (for calc_dict)"""
        mod = self.py_mods.by_path[module_path]
        self.py_mods.set_imports(mod)
        # filter out imports not being tracked
        return {'file_dep': [dep for dep in mod.imports if dep in self.py_files]}


    @staticmethod
    def _acc_dep(mod, dependencies):
        """action: get direct and indirect dependencies"""
        acc = ["acc_dep:%s" %m for m in dependencies]
        return {
            'calc_dep': acc,
            'file_dep': list(dependencies)
            }


    def gen_deps(self):
        """get direct dependencies for each module"""
        for mod in self.py_files:
            # direct dependencies
            yield {
                'basename': 'get_dep',
                'name': mod,
                'actions':[(self._get_dep, [mod])],
                'file_dep': [mod],
                'uptodate': [result_dep('watched_files')],
                }

            # accumulated dependencies
            yield {
                'basename': 'acc_dep',
                'name': mod,
                'actions': [(self._acc_dep, [mod])],
                'file_dep': [mod],
                'calc_dep': ["get_dep:%s" % mod],
                'uptodate': [result_dep('watched_files')],
                }

            # dumb task just to make it easy to
            # retrieve all file_dep (recursivelly)
            yield {
                'basename': '_all_deps',
                'name': mod,
                'actions': None,
                'file_dep': [mod],
                'calc_dep': ["acc_dep:%s" % mod],
                'verbosity': 0,
                }

    def gen_outdated(self, test_files):
        """find which tests are not up-to-date"""
        for test in test_files:
            yield {
                'basename': 'outdated',
                'name': test,
                'actions': [lambda : False], # always fail if executed
                'file_dep': [test],
                'calc_dep': ["acc_dep:%s" % test],
                'verbosity': 0,
                }


def task_gen():
    """genrate all tasks"""
    inc = IncrementalTasks(PY_FILES)
    yield inc.gen_watched_files()
    yield inc.gen_deps()
    yield inc.gen_outdated(TEST_FILES)


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
        if task.name.startswith('outdated:'):
            return
        raise pytest.UsageError("%s:%s" % (task.name, exception))
    def add_success(self, task):
        pass
    def skip_uptodate(self, task):
        pass
    def skip_ignore(self, task):
        pass
    def cleanup_error(self, exception):
        pass
    def runtime_error(self, msg):
        raise Exception(msg)
    def teardown_task(self, task):
        pass
    def complete_run(self):
        self.outstream.write("%r" % self.outdated)

### XXX remove this crap
TEST_FILES = []
PY_FILES = [] # list of files being tracked for changes

def constants(py_files, test_files):
    PY_FILES[:] = list(set(py_files + test_files))
    TEST_FILES[:] = test_files


##################### end doit section

import glob
import pytest

def pytest_addoption(parser):
    group = parser.getgroup("incremental", "incremental testing")
    group.addoption(
        '--incremental', action="store_true",
        dest="incremental", default=False,
        help="execute only outdated tests (based on modified files)")
    group.addoption(
        '--watch-path', action="append",
        dest="watch_path", default=[],
        help="file path of a package. watch for file changes in packages (multi-allowed)")
    group.addoption(
        '--list-outdated', action="store_true",
        dest="list_outdated", default=False,
        help="print list of outdated test files")
    group.addoption(
        '--list-dependencies', action="store_true",
        dest="list_dependencies", default=False,
        help="print list of python modules being tracked and its dependencies")
    group.addoption(
        '--graph-dependencies', action="store_true",
        dest="graph_dependencies", default=False,
        help="create graph file of dependencies in dot format 'imports.dot'")


def pytest_configure(config):
    if (config.option.incremental or
        config.option.list_outdated or
        config.option.list_dependencies or
        config.option.graph_dependencies
        ):
        config._incremental = IncrementalPlugin()
        config.pluginmanager.register(config._incremental)


def pytest_unconfigure(config):
    incremental_plugin = getattr(config, '_incremental', None)
    if incremental_plugin:
        del config._incremental
        config.pluginmanager.unregister(incremental_plugin)


class IncrementalPlugin(object):
    """pytest-incremental plugin class

    @cvar DB_FILE: (str) file name used as doit db file
    @ivar tasks: (dict) with reference to doit tasks
    @ivar py_files: (list - str) relative path of test and code under test
    @ivar success: (list - str) path of test files (of tests that succeed)
    @ivar fail: (list - str) path of test files (of tests that failed)
    @ivar uptodate: (list - pytest.Item) wont be executed
    @ivar pkg_folders

    how it works
    =============

    * pytest_sessionstart: check configuration,
                           find python files (if pkg specified)
    * pytest_collect_file: to find out python files that doit will keep track
                           (if pkg not specified)
    * pytest_collection_modifyitems (get_outdated): run doit and remove
             up-to-date tests from test items
    * pytest_runtestloop: print info on up-to-date (not excuted) on terminal
    * pytest_runtest_makereport: collect result from individual tests
    * pytest_testnodedown: (xdist) send result from slave to master
    * pytest_sessionfinish (set_success): save successful tasks in doit db
    """

    DB_FILE = '.pytest-incremental'

    def __init__(self):
        self.task_list = None
        self.py_files = []
        self.success = set()
        self.fail = set()
        self.uptodate = None
        self.pkg_folders = None

        self.list_outdated = False
        self.list_dependencies = False
        self.graph_dependencies = False
        self.run = None

        self.type = None # one of (normal, master, slave)
        self.test_files = None # required for xdist


    def _run_doit(self, test_files, output, sel_tasks):
        """load this file as dodo file to collect tasks"""
        constants(self.py_files, list(test_files))
        config = {'dep_file': self.DB_FILE,
                  'continue': True,
                  'reporter': OutdatedReporter,
                  'outfile': output,
                  }
        ctx = globals()
        ctx['DOIT_CONFIG'] = config
        loader = ModuleTaskLoader(ctx)
        cmd = Run(task_loader=loader)
        cmd.parse_execute(sel_tasks)
        self.task_list = cmd.task_list


    def get_outdated(self, test_files):
        """run doit to find out which test files are "outdated"
        A test file is outdated if there was a change in the content in any
        import (direct or indirect) since last succesful execution
        """
        # lock for parallel access to DB
        if self.type == 'slave':
            lock_file = '.pytest-incremental-lock'
            lock_fd = open(lock_file, 'w')
            fcntl.lockf(lock_fd, fcntl.LOCK_EX)
        try:
            output = StringIO.StringIO()
            outdated_tasks = ["outdated:%s" % path for path in test_files]
            self._run_doit(test_files, output, outdated_tasks)
        finally:
            if self.type == 'slave':
                fcntl.lockf(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
        output.seek(0)
        got = output.read()
        return got


    def set_success(self, test_files):
        """mark doit test tasks as sucessful"""
        task_dict = dict((t.name, t) for t in self.task_list)
        db = Dependency(self.DB_FILE)
        for path in test_files:
            task_name = "outdated:%s" % path
            db.save_success(task_dict[task_name])
        db.close()


    def _get_pkg_modules(self, pkg_name):
        """get all package modules recursively"""
        pkg_glob = os.path.join(pkg_name, "*.py")
        this_modules = glob.glob(pkg_glob)
        for dirname, dirnames, filenames in os.walk(pkg_name):
            for subdirname in dirnames:
                sub_path = os.path.join(dirname, subdirname)
                if _PyModule.is_pkg(sub_path):
                    this_modules.extend(self._get_pkg_modules(sub_path))
        return this_modules


    def _check_cmd_options(self, config):
        """sanity checking"""
        if not self.pkg_folders:
            if not (len(config.args) == 1 and
                    config.args[0] == os.getcwd()):
                msg = ("(plugin-incremental) You are required to setup "
                       "--watch-path in order to use the plugin together "
                       "with an path argument.")
                raise pytest.UsageError(msg)
            if self.type == "master":
                msg = ("(plugin-incremental) You are required to setup "
                       "--watch-path in order to use the plugin together "
                       "with plugin-xdist")
                raise pytest.UsageError(msg)

    def _set_type(self, session):
        """figure out what type of node (xdist) we are in.
        'normal' if not using xdist
        or master/slave
        """
        session_name = session.__class__.__name__
        if (session.config.pluginmanager.hasplugin('dsession') or
            session_name == 'DSession'):
            return "master"
        elif (hasattr(session.config, 'slaveinput') or
              session_name == 'SlaveSession'):
            return "slave"
        else:
            return "normal"


    def pytest_sessionstart(self, session):
        """initialization and sanity checking"""
        self.type = self._set_type(session)
        self.pkg_folders = session.config.option.watch_path
        self.list_outdated = session.config.option.list_outdated
        self.list_dependencies = session.config.option.list_dependencies
        self.graph_dependencies = session.config.option.graph_dependencies
        self.run = not any((self.list_outdated,
                            self.list_dependencies,
                            self.graph_dependencies))

        self._check_cmd_options(session.config)
        if self.pkg_folders:
            for pkg in self.pkg_folders:
                self.py_files.extend(self._get_pkg_modules(pkg))


    def pytest_collect_file(self, path, parent):
        """collect python files"""
        if (not self.pkg_folders) and path.strpath.endswith('.py'):
            self.py_files.append(os.path.relpath(path.strpath))


    def pytest_collection_modifyitems(self, session, config, items):
        """filter out up-to-date tests"""
        # called on slave only!
        test_files = set((i.location[0] for i in items))
        self.test_files = test_files
        # list dependencies doesnt care about current state of outdated
        if self.list_dependencies or self.graph_dependencies:
            return
        outdated_str = self.get_outdated(test_files)
        outdated = set(eval(outdated_str))
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
        """print up-to-date tests info before running tests or...
        if --list-outdated just print the outdated ones (and dont run tests)
        """
        if self.run:
            self.print_uptodate_test_files()
            return

        # print info commands
        if self.list_outdated:
            self.print_outdated()
        elif self.list_dependencies:
            self.print_deps()
        elif self.graph_dependencies:
            self.create_dot_graph()
        return 0 # dont execute tests


    def print_uptodate_test_files(self):
        """print info on up-to-date tests"""
        uptodate_test_files = set((item.location[0] for item in self.uptodate))
        if uptodate_test_files:
            print
        for test_file in sorted(uptodate_test_files):
            print "%s  [up-to-date]" % test_file

    def print_outdated(self):
        """print list of outdated test files"""
        uptodate_test_files = set((item.location[0] for item in self.uptodate))
        outdated = []
        for test in self.test_files:
            if test not in uptodate_test_files:
                outdated.append(test)

        print
        if outdated:
            print "List of outdated test files:"
            for test in sorted(outdated):
                print test
        else:
            print "All test files are up to date"


    def print_deps(self):
        """print list of all python modules being tracked and its dependencies"""
        self._run_doit(self.test_files, StringIO.StringIO(), ['_all_deps'])
        dep_dict = {}
        for task in self.task_list:
            if task.name.startswith('_all_deps:'):
                dep_dict[task.name[10:]] = sorted(task.file_dep)
        for name in sorted(dep_dict):
            print "%s: %s" % (name, ", ".join(dep_dict[name]))

    def create_dot_graph(self):
        """create a graph of imports in dot format
        dot -Tpng -o imports.png imports.dot
        """
        self.task_list = self._load_tasks(self.test_files)
        doit_run(self.DB_FILE, self.task_list, StringIO.StringIO(), ['get_dep'],
                 continue_=True, reporter=OutdatedReporter)
        dep_dict = {}
        for task in self.task_list:
            if task.name.startswith('get_dep:'):
                dep_dict[task.name[8:]] = task.values['file_dep']
        with open('imports.dot', 'w') as dot_file:
            dot_file.write('digraph imports {\n')
            for name, imports in dep_dict.iteritems():
                if name in self.test_files:
                    dot_file.write('"%s" [color = red]\n' % name)
                for imported in imports:
                    line = ('"%s" -> "%s"\n' % (name, imported))
                    dot_file.write(line)
            dot_file.write('}\n')


    def pytest_runtest_logreport(self, report):
        """save success and failures result so we can decide which files
        should be marked as successful in doit
        """
        if report.failed:
            self.fail.add(report.location[0])
        else:
            self.success.add(report.location[0])


    def pytest_testnodedown(self, node, error):
        """collect info from slave node"""
        # this method is only called from master
        self.success.update(node.slaveoutput['success'])
        self.fail.update(node.slaveoutput['fail'])
        if not self.test_files:
            self.test_files = node.slaveoutput['test_files']


    def pytest_sessionfinish(self, session):
        """save success in doit"""
        if not self.run:
            return
        if self.type == 'slave':
            config = session.config
            config.slaveoutput['success'] = self.success
            config.slaveoutput['fail'] = self.fail
            config.slaveoutput['test_files'] = self.test_files
            return
        elif self.type == "master":
            self.task_list = self._load_tasks(self.test_files)
            # we need to make sure task have all calc_dep calculated
            doit_run(self.DB_FILE, self.task_list, StringIO.StringIO(),
                     ['outdated'],
                     continue_=True, reporter=OutdatedReporter)

        # debug messages
        # print
        # print "SUCCESS:", self.success
        # print "FAIL:", self.fail

        if self.task_list is None:
            return

        # FIXME: need to check if all test were executed
        # in case -k is used. by now just consider not all were executed.
        if not getattr(session.config.option, 'keyword', None):
            self.set_success(list(self.success - self.fail))
