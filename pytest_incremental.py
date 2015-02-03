"""
pytest-incremental : an incremental test runner (pytest plugin)
https://pypi.python.org/pypi/pytest-incremental

The MIT License - see LICENSE file
Copyright (c) 2011-2015 Eduardo Naufel Schettino
"""

from __future__ import print_function
from __future__ import unicode_literals

__version__ = (0, 4, 'dev0')

import os
import ast
import fcntl
import json
from collections import deque

try:
    # PY 3
    import io
    StringIO = io.StringIO
except ImportError: # pragma: no cover
    # PY 2
    import StringIO
    StringIO = StringIO.StringIO


from doit.task import Task, DelayedLoader
from doit.dependency import Dependency
from doit.cmd_base import ModuleTaskLoader
from doit.cmd_run import Run
from doit.tools import config_changed

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
    """Represents a python module

    :path: (str) path to module
    :ivar: fqn (list - str) full qualified name as list of strings
    """
    def __init__(self, path):
        self.path = path
        self.fqn = self._get_fqn(path)

    def __repr__(self): # pragma: no cover
        return "<_PyModule %s>" % self.path

    @staticmethod
    def is_pkg(path):
        return (os.path.isdir(path) and
                os.path.exists(os.path.join(path, '__init__.py')))

    @classmethod
    def _get_fqn(cls, path):
        """get full qualified name as list of strings
        @return list (str) of path segments from top package to given path
        """
        name_list = []
        current_path = os.path.basename(path)
        if current_path.endswith('.py'):
            current_path = current_path[:-3]
        parent_path = os.path.dirname(path)
        # move to parent path until parent path is a python package
        while True:
            name_list.append(current_path)
            if not cls.is_pkg(parent_path):
                break
            current_path = os.path.basename(parent_path)
            parent_path = os.path.dirname(parent_path)
        name_list.reverse()
        return name_list



class ModuleSet(object):
    """helper to filter import list only from within packages"""
    def __init__(self, path_list):
        self.pkgs = set() # str of fqn (dot separed)
        self.by_path = {} # module by path
        self.by_name = {} # module by name (dot separated)

        for path in path_list:
            # create modules object
            mod = _PyModule(path)
            if mod.fqn[-1] == '__init__':
                self.pkgs.add('.'.join(mod.fqn[:-1]))
            self.by_path[path] = mod
            self.by_name['.'.join(mod.fqn)] = mod


    def _get_imported_module(self, module_name, relative_guess=''):
        """try to get imported module reference by its name"""
        # if imported module on module_set add to list
        imp_mod = self.by_name.get(module_name)
        if imp_mod:
            return imp_mod

        # last part of import section might not be a module
        # remove last section
        only = module_name.rsplit('.', 1)[0]
        # when removing last section, need to remove relative_guess to
        # avoid importing its own package
        only = only[len(relative_guess):]
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


    def get_imports(self, module):
        """return set of imported modules that are in self
        :param module: _PyModule
        :return: (set - str) of path names
        """
        module_pkg = '.'.join(module.fqn[:-1])
        imports = set()
        raw_imports = find_imports(module.path)
        for import_entry in raw_imports:
            # join 'from' and 'import' part of import statement
            full = ".".join(s for s in import_entry[:2] if s)

            import_level = import_entry[3]
            if import_level:
                # intra package imports
                intra = '.'.join(module.fqn[:-import_level] + [full])
                imported = self._get_imported_module(intra)
                if imported:
                    imports.add(imported.path)

            else:
                # deal with old-style relative imports
                full_relative = "%s.%s" % (module_pkg, full)
                imported = self._get_imported_module(full_relative, module_pkg)
                if imported:
                    imports.add(imported.path)
                else:
                    imported = self._get_imported_module(full)
                    if imported:
                        imports.add(imported.path)
        return imports


######### Graph implementation

class GNode(object):
    def __init__(self, name):
        self.name = name
        self.deps = set() # of direct GNode deps
        # all_deps are lazily calculated and cached
        self._all_deps = None # set of all (recursive) deps names
        # when a cyclic dependency is found copy_from indicated
        # which GNode depepencies should be copied from (all nodes
        # in a cycle have the same set of dependencies)
        self.copy_from = None

    def __repr__(self):
        return "<GNode({})>".format(self.name)

    def add_dep(self, dep):
        """add a dependency of self"""
        self.deps.add(dep)

    def all_deps(self, stack=None):
        """return set of GNode with all deps from this node (including self)"""
        # return value if already calculated
        if self._all_deps is not None:
            return self._all_deps

        # stack is used to detect cyclic dependencies
        if stack is None:
            stack = set()

        stack.add(self)
        deps = set([self]) # keep track of all deps
        to_process = deque(self.deps) # deps found but not processed yet
        # recursive descend to all deps
        while to_process:
            node = to_process.popleft()
            deps.add(node)
            # cycle detected, copy dependencies from the first node in the cycle
            if node in stack:
                self.copy_from = node
                continue
            # if node in cycle that was already processed, skip
            if node.copy_from and node.copy_from in deps:
                continue
            # recursive add deps
            for got in node.all_deps(stack):
                if got not in deps:
                    to_process.append(got)

        stack.remove(self)

        # node deps will be copied but need to return deps out of cycle
        if self.copy_from:
            return deps

        self._all_deps = deps
        # finish processing of a sub-tree, set all copies
        if not stack:
            for node in deps:
                if node.copy_from:
                    node._all_deps = node.copy_from._all_deps
                    node.copy_from = None
        return self._all_deps


class DepGraph(object):
    NODE_CLASS = GNode
    def __init__(self, dep_dict):
        """
        :param dep_dict: (dict) key: (str) node name
                                value: (list - str) direct deps
        """
        self.nodes = {}
        for name, deps in dep_dict.items():
            node = self._node(name)
            for dep in deps:
                node.add_dep(self._node(dep))

    def _node(self, name):
        """get or create node"""
        node = self.nodes.get(name, None)
        if not node:
            node = self.nodes[name] = self.NODE_CLASS(name)
        return node


    def write_dot(self, stream):
        """write dot file
        @param info_list
        """
        stream.write("digraph imports {\n")
        for node in self.nodes.values():
            if node.name.startswith('test'):
                continue
            for dep in node.deps:
                stream.write("%s -> %s\n" % (
                    node.name.replace('/', '_').replace('.', '_'),
                    dep.name.replace('/', '_').replace('.', '_')))
        stream.write("}\n")


######### start doit section

class IncrementalTasks(object):
    """generate doit tasks used by pytest-incremental

    @ivar py_mods (ModuleSet)
    @ivar py_files (list - str): files being watched for changes
    """
    def __init__(self, py_files, test_files):
        self.py_files = list(set(py_files + test_files))
        self.test_files = test_files[:]
        self.py_mods = ModuleSet(self.py_files)


    def _get_dep(self, module_path):
        """action: return list of directed imported modules"""
        mod = self.py_mods.by_path[module_path]
        return {'imports': list(self.py_mods.get_imports(mod))}


    def write_json_deps(self, imports):
        result = {k: v['imports'] for k,v in imports.items()}
        with open('deps.json', 'w') as fp:
            json.dump(result, fp)

    @staticmethod
    def write_dot(file_name, graph):
        with open(file_name, "w") as fp:
            graph.write_dot(fp)


    def gen_deps(self):
        """get direct dependencies for each module"""
        watched_modules = str(list(sorted(self.py_files)))
        for mod in self.py_files:
            # direct dependencies
            yield {
                'basename': 'get_dep',
                'name': mod,
                'actions':[(self._get_dep, [mod])],
                'file_dep': [mod],
                'uptodate': [config_changed(watched_modules)],
                }
        yield {
            'basename': 'dep-json',
            'actions': [self.write_json_deps],
            'getargs': {'imports': ('get_dep', None)},
            'targets': ['deps.json'],
        }

        # FIXME extract this into a helper function
        loader = DelayedLoader(self.gen_print_deps, executed='dep-json')
        yield Task('print-deps', None, loader=loader)

    def gen_print_deps(self):
        with open('deps.json') as fp:
            deps = json.load(fp)
        graph = DepGraph(deps)
        for node in graph.nodes.values():
            yield {
                'basename': 'print-deps',
                'name': node.name,
                'actions': [(lambda node: print(node.all_deps()), [node])],
                'verbosity': 2,
            }


        yield {
            'basename': 'print-deps',
            'name': 'dot',
            'actions': [(self.write_dot, ['deps.dot', graph])],
            'file_dep': ['deps.json'],
            'targets': ['deps.dot'],
        }

        yield {
            'basename': 'print-deps',
            'name': 'jpeg',
            'actions': ["dot -Tpng -o %(targets)s %(dependencies)s"],
            'file_dep': ['deps.dot'],
            'targets': ["deps.png"],
        }


        # generate tasks used by py.test to save successful results
        for test in self.test_files:
            yield {
                'basename': 'outdated',
                'name': test,
                'actions': [lambda : False], # always fail if executed
                'file_dep': [n.name for n in graph.nodes[test].all_deps()],
                'verbosity': 0,
                }

    def create_doit_tasks(self):
        """magic method used by doit to create tasks """
        yield self.gen_deps()




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
        inc = IncrementalTasks(self.py_files, list(test_files))
        config = {'dep_file': self.DB_FILE,
                  'continue': True,
                  'reporter': OutdatedReporter,
                  'outfile': output,
                  }
        ctx = {'tasks_generator': inc,
               'DOIT_CONFIG': config
               }
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
            output = StringIO()
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
                       "with a path argument.")
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
            self.py_files.append(os.path.abspath(path.strpath))


    def pytest_collection_modifyitems(self, session, config, items):
        """filter out up-to-date tests"""
        # called on slave only!
        test_files = set((os.path.abspath(i.location[0]) for i in items))
        self.test_files = test_files
        # list dependencies doesnt care about current state of outdated
        if self.list_dependencies or self.graph_dependencies:
            return
        outdated_str = self.get_outdated(test_files)
        outdated_list = eval(outdated_str)
        outdated = set(outdated_list)
        selected = []
        deselected = []
        for colitem in items:
            path = os.path.abspath(colitem.location[0])
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
            print()
        for test_file in sorted(uptodate_test_files):
            print("{}  [up-to-date]".format(test_file))

    def print_outdated(self):
        """print list of outdated test files"""
        uptodate_test_files = set((os.path.abspath(item.location[0]) for item in self.uptodate))
        outdated = []
        for test in self.test_files:
            if test not in uptodate_test_files:
                outdated.append(test)

        print()
        if outdated:
            print("List of outdated test files:")
            for test in sorted(outdated):
                print(test)
        else:
            print("All test files are up to date")


    def print_deps(self):
        """print list of all python modules being tracked and its dependencies"""
        self._run_doit(self.test_files, StringIO(), ['_all_deps'])
        dep_dict = {}
        for task in self.task_list:
            if task.name.startswith('_all_deps:'):
                dep_dict[task.name[10:]] = sorted(task.file_dep)
        for name in sorted(dep_dict):
            print("{}: {}".format(name, ", ".join(dep_dict[name])))

    def create_dot_graph(self):
        """create a graph of imports in dot format
        dot -Tpng -o imports.png imports.dot
        """
        self._run_doit(self.test_files, StringIO(), ['get_dep'])
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
            # we need to make sure task have all calc_dep calculated
            outdated_tasks = ["outdated:%s" % path for path in self.test_files]
            self._run_doit(self.test_files, StringIO(), outdated_tasks)

        # debug messages
        # print
        # print("SUCCESS:", self.success)
        # print("FAIL:", self.fail)

        if self.task_list is None:
            return

        # FIXME: need to check if all test were executed
        # in case -k is used. by now just consider not all were executed.
        if not getattr(session.config.option, 'keyword', None):
            successful = [os.path.abspath(f) for f in (self.success - self.fail)]
            self.set_success(successful)
