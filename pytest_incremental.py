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
import functools
from collections import deque, defaultdict

import six
from six import StringIO


from doit.task import Task, DelayedLoader
from doit.dependency import Dependency
from doit.cmd_base import ModuleTaskLoader
from doit.cmd_run import Run
from doit.reporter import ZeroReporter
from doit import doit_cmd
from doit.tools import config_changed

############# find imports using AST

def _file2ast(file_name):
    """get ast-tree from file_name"""
    with open(file_name, 'r') as fp:
        text = fp.read()
    return ast.parse(text, file_name)

class _ImportsFinder(ast.NodeVisitor):
    """find all imports
    :ivar imports: (list - tuple) (module, name, asname, level)
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
    :return: (list - tuple) (module, name, asname, level)
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
        """return True if path is a python package"""
        return (os.path.isdir(path) and
                os.path.exists(os.path.join(path, '__init__.py')))

    @classmethod
    def _get_fqn(cls, path):
        """get full qualified name as list of strings
        :return: (list - str) of path segments from top package to given path
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
        no_obj = module_name.rsplit('.', 1)[0]
        imp_mod2 = self.by_name.get(no_obj)
        if imp_mod2:
            return imp_mod2

        # special case for __init__
        if module_name in self.pkgs:
            pkg_name = module_name  + ".__init__"
            return self.by_name[pkg_name]

        # when removing last section (obj), need to remove relative_guess to
        # avoid importing its own package
        no_rel_no_obj = no_obj[len(relative_guess):]
        if no_rel_no_obj in self.pkgs:
            pkg_name = no_rel_no_obj +  ".__init__"
            return self.by_name[pkg_name]


    def get_imports(self, module):
        """return set of imported modules that are in self
        :param module: _PyModule
        :return: (set - str) of path names
        """
        # print('####', module.fqn)
        # print(self.by_name.keys(), '\n\n')
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
                for level in range(1, len(module.fqn)):
                    module_pkg = '.'.join(module.fqn[:-level])
                    full_relative = "%s.%s" % (module_pkg, full)
                    imported = self._get_imported_module(full_relative, module_pkg)
                    if imported:
                        imports.add(imported.path)
                        break
                else:
                    imported = self._get_imported_module(full)
                    if imported:
                        imports.add(imported.path)
        return imports


######### Graph implementation

class GNode(object):
    '''represents a node in a direct graph

    Designed to efficiently return a list of all nodes in a sub-graph.
    The sub-graph from each node is built on demand and cached after built.
    '''
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
    '''A direct graph used to track python module dependencies'''
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
        :param stream: Any object with a `write()` method
        """
        stream.write("digraph imports {\n")
        for node in self.nodes.values():
            # FIXME add option to include test files or not
            #if node.name.startswith('test'):
            #    continue
            node_path = os.path.relpath(node.name)
            if node.deps:
                for dep in node.deps:
                    dep_path = os.path.relpath(dep.name)
                    stream.write('"{}" -> "{}"\n'.format(node_path, dep_path))
            else:
                stream.write('"{}"\n'.format(node_path))
        stream.write("}\n")


######### start doit section

def gen_after(name, after_task):
    '''decorator for function creating a DelayedTask'''
    def decorated(fn_creator):
        """yield DelayedTasks executed after `after_task` is executed"""
        def task_creator(self):
            '''create a Task setting its loader'''
            creator = functools.partial(fn_creator, self)
            loader = DelayedLoader(creator, executed=after_task)
            return Task(name, None, loader=loader)
        return task_creator
    return decorated


class PyTasks(object):
    """generate doit tasks related to python modules import dependencies

    :ivar ModuleSet py_mods:
    :ivar py_files: (list - str) files being watched for changes
    :ivar json_file str: name of intermediate file with import info from all
                         modules
    """
    def __init__(self, py_files, json_file='deps.json'):
        self.json_file = json_file
        self.py_files = list(set(py_files))
        self.py_mods = ModuleSet(self.py_files)
        self._graph = None # DepGraph cached on first use

    @property
    def graph(self):
        """create Graph from json file"""
        if self._graph is None:
            with open(self.json_file) as fp:
                deps = json.load(fp)
            self._graph = DepGraph(deps)
        return self._graph


    def action_get_dep(self, module_path):
        """action: return list of direct imports from a single py module

        :return dict: single value 'imports', value set of str file paths
        """
        mod = self.py_mods.by_path[module_path]
        return {'imports': list(self.py_mods.get_imports(mod))}


    def action_write_json_deps(self, imports):
        """write JSON file with direct imports of all modules"""
        result = {k: v['imports'] for k, v in imports.items()}
        with open(self.json_file, 'w') as fp:
            json.dump(result, fp)

    def gen_deps(self):
        """generate doit tasks to find imports

        generated tasks:
            * get_dep:<path> => find imported moudules
            * dep-json => save import info in a JSON file
        """
        watched_modules = str(list(sorted(self.py_files)))
        for mod in self.py_files:
            # direct dependencies
            yield {
                'basename': 'get_dep',
                'name': mod,
                'actions':[(self.action_get_dep, [mod])],
                'file_dep': [mod],
                'uptodate': [config_changed(watched_modules)],
                }

        # Create an intermediate json file with import information.
        # It is required to create an intermediate file because DelayedTasks
        # can not have get_args to use values from other tasks.
        yield {
            'basename': 'dep-json',
            'actions': [self.action_write_json_deps],
            'task_dep': ['get_dep'],
            'getargs': {'imports': ('get_dep', None)},
            'targets': [self.json_file],
            'doc': 'save dep info in {}'.format(self.json_file),
        }


    @staticmethod
    def action_print_dependencies(node):
        '''print a node's name and its dependencies to SDTOUT'''
        node_list = sorted(n.name for n in node.all_deps())
        node_path = os.path.relpath(node.name)
        deps_path = (os.path.relpath(p) for p in node_list)
        print(' - {}: {}'.format(node_path, ', '.join(deps_path)))

    @gen_after(name='print-deps', after_task='dep-json')
    def gen_print_deps(self):
        '''create tasks for printing node info to STDOUT'''
        for node in self.graph.nodes.values():
            yield {
                'basename': 'print-deps',
                'name': node.name,
                'actions': [(self.action_print_dependencies, [node])],
                'verbosity': 2,
            }



    @staticmethod
    def action_write_dot(file_name, graph):
        """write a dot-file(graphviz) with import relation of modules"""
        with open(file_name, "w") as fp:
            graph.write_dot(fp)


    @gen_after(name='dep-graph', after_task='dep-json')
    def gen_dep_graph(self, dot_file='deps.dot', png_file='deps.png'):
        """generate tasks for creating a `dot` graph of module imports"""
        yield {
            'basename': 'dep-graph',
            'name': 'dot',
            'actions': [(self.action_write_dot, ['deps.dot', self.graph])],
            'file_dep': [self.json_file],
            'targets': [dot_file],
        }

        # generate PNG with bottom-up tree
        dot_cmd = 'dot -Tpng -Grankdir=BT '
        yield {
            'basename': 'dep-graph',
            'name': 'jpeg',
            'actions': [dot_cmd + " -o %(targets)s %(dependencies)s"],
            'file_dep': [dot_file],
            'targets': [png_file],
        }




class IncrementalTasks(PyTasks):
    """Manage creation of all tasks for pytest-incremental plugin"""

    def __init__(self, pyfiles, test_files=None, **kwargs):
        PyTasks.__init__(self, pyfiles, **kwargs)
        self.test_files = test_files

    def check_success(self):
        """check if task should succeed based on GLOBAL parameter"""
        return doit_cmd.get_var('success', False)

    @gen_after(name='outdated', after_task='dep-json')
    def gen_outdated(self):
        """generate tasks used by py.test to keep-track of successful results"""
        nodes = self.graph.nodes
        for test in self.test_files:
            yield {
                'basename': 'outdated',
                'name': test,
                'actions': [self.check_success],
                'file_dep': [n.name for n in nodes[test].all_deps()],
                'verbosity': 0,
                }

    def create_doit_tasks(self):
        '''create all tasks used by the incremental plugin
        This method is a hook used by doit
        '''
        yield self.gen_deps()
        yield self.gen_print_deps()
        yield self.gen_dep_graph()
        yield self.gen_outdated()



class OutdatedReporter(ZeroReporter):
    """A doit reporter specialized to return list of outdated tasks"""
    def __init__(self, outstream, options):
        self.outdated = []
        self.outstream = outstream

    def execute_task(self, task):
        if task.name.startswith('outdated:'):
            self.outdated.append(task.name.split(':', 1)[1])

    def add_failure(self, task, exception):
        if task.name.startswith('outdated'):
            return
        raise pytest.UsageError("%s:%s" % (task.name, exception))

    def runtime_error(self, msg):
        raise Exception(msg)

    def complete_run(self):
        outdated_info = json.dumps(self.outdated)
        self.outstream.write(six.u(outdated_info))


##################### end doit section


class IncrementalControl(object):
    '''control which modules need to execute tests

    :cvar str DB_FILE: file name used as doit db file
    :ivar py_files: (list - str) relative path of test and code under test
    '''
    DB_FILE = '.pytest-incremental'

    def __init__(self, pkg_folders):
        assert isinstance(pkg_folders, list)
        self.test_files = None
        self.py_files = []
        for pkg in pkg_folders:
            self.py_files.extend(self._get_pkg_modules(pkg))

    def _get_pkg_modules(self, pkg_name, get_sub_folders=True):
        """get all package modules recursively
        :param pkg_name: (str) path to search for python modules
        :param get_sub_folders: (bool) search sub-folders even if they are
                                not python packages
        """
        pkg_glob = os.path.join(pkg_name, "*.py")
        this_modules = glob.glob(pkg_glob)
        for dirname, dirnames, filenames in os.walk(pkg_name):
            for subdirname in dirnames:
                sub_path = os.path.join(dirname, subdirname)
                if get_sub_folders or _PyModule.is_pkg(sub_path):
                    this_modules.extend(self._get_pkg_modules(sub_path))
        return this_modules

    def _run_doit(self, sel_tasks, doit_vars=None):
        """load this file as dodo file to collect tasks"""
        inc = IncrementalTasks(self.py_files, test_files=list(self.test_files))
        output = StringIO()
        config = {
            'dep_file': self.DB_FILE,
            'continue': True,
            'reporter': OutdatedReporter,
            'outfile': output,
        }
        ctx = {
            'tasks_generator': inc,
            'DOIT_CONFIG': config,
        }
        doit_cmd.reset_vars()
        if doit_vars:
            for key, value in doit_vars.items():
                doit_cmd.set_var(key, value)
        loader = ModuleTaskLoader(ctx)
        cmd = Run(task_loader=loader)
        cmd.parse_execute(sel_tasks)
        output.seek(0)
        return output.read()


    def get_outdated(self):
        """run doit to find out which test files are "outdated"
        A test file is outdated if there was a change in the content in any
        import (direct or indirect) since last succesful execution

        :return set(str): list of outdated files
        """
        outdated_tasks = ['outdated']
        output_str = self._run_doit(outdated_tasks)
        return set(json.loads(output_str))

    def save_success(self, success):
        """mark doit test tasks as sucessful"""
        tasks = ['dep-json']
        for path in success:
            tasks.append("outdated:%s" % path)
        self._run_doit(tasks, doit_vars={'success':True})


    def print_deps(self):
        """print list of all python modules being tracked and its dependencies"""
        self._run_doit(['print-deps'])

    def create_dot_graph(self):
        """create a graph of imports in dot format
        """
        self._run_doit(['dep-graph'])



### py.test integration

import glob
import pytest

def pytest_addoption(parser):
    '''py.test hook: register argparse-style options and config values'''
    group = parser.getgroup("incremental", "incremental testing")
    group.addoption(
        '--inc', action="store_true",
        dest="incremental", default=False,
        help="execute only outdated tests (based on modified files)")
    group.addoption(
        '--inc-path', action="append",
        dest="watch_path", default=[],
        help="file path of a package. watch for file changes in packages (multi-allowed)")
    group.addoption(
        '--inc-outdated', action="store_true",
        dest="list_outdated", default=False,
        help="print list of outdated test files")
    group.addoption(
        '--inc-deps', action="store_true",
        dest="list_dependencies", default=False,
        help="print list of python modules being tracked and its dependencies")
    group.addoption(
        '--inc-graph', action="store_true",
        dest="graph_dependencies", default=False,
        help="create graph file of dependencies in dot format 'deps.dot'")


def pytest_configure(config):
    '''Register incremental plugin only if any of its options is specified

    py.test hook: called after parsing cmd optins and loading plugins.
    '''
    opt = config.option
    if any((opt.incremental, opt.list_outdated, opt.list_dependencies,
            opt.graph_dependencies)):
        config._incremental = IncrementalPlugin()
        config.pluginmanager.register(config._incremental)


def pytest_unconfigure(config):
    '''py.test hook: called before test process is exited.'''
    incremental_plugin = getattr(config, '_incremental', None)
    if incremental_plugin:
        del config._incremental
        config.pluginmanager.unregister(incremental_plugin)



class IncrementalPlugin(object):
    """pytest-incremental plugin class

    how it works
    =============

    * pytest_sessionstart: check configuration,
                           find python files (if pkg specified)
    * pytest_collection_modifyitems (get_outdated): run doit and remove
             up-to-date tests from test items
    * pytest_runtestloop: print info on up-to-date (not excuted) on terminal
    * pytest_runtest_logreport: collect result from individual tests
    * pytest_sessionfinish (save_success): save successful tasks in doit db
    """

    def __init__(self):
        # command line options
        self.list_outdated = False
        self.list_dependencies = False
        self.graph_dependencies = False
        self.run = None

        # IncrementalControl, set on sessionstart
        self.control = None

        # test information gathering during collect phase
        self.uptodate_paths = set()  # test paths that are up-to-date
        self.outofdate = defaultdict(list)  # path: list of nodeid
        self.test_files = None  # list of collected test files

        # sets of nodeid's set on logreport
        self.passed = set()
        self.failed = set()


    def pytest_sessionstart(self, session):
        """initialization and sanity checking"""
        if session.config.pluginmanager.hasplugin('dsession'):
            msg = 'Plugin incremental is not compatible with plugin xdist.'
            raise pytest.UsageError(msg)

        opts = session.config.option
        self.list_outdated = opts.list_outdated
        self.list_dependencies = opts.list_dependencies
        self.graph_dependencies = opts.graph_dependencies
        self.run = not any((self.list_outdated,
                            self.list_dependencies,
                            self.graph_dependencies))

        # pkg_folders to watch can never be empty, if not specified use CWD
        pkg_folders = session.config.option.watch_path
        if not pkg_folders:
            pkg_folders.append(os.getcwd())

        self.control = IncrementalControl(pkg_folders)


    def pytest_collection_modifyitems(self, session, config, items):
        """py.test hook: reset `items` removing tests from up-to-date modules

        side-effects:
        - set self.test_files with all test modules
        - set self.uptodate_paths with all test files that wont be executed
        - set the param `items` with items to be executed
        """
        # save reference of all found test modules
        test_files = set((str(i.fspath) for i in items))
        self.test_files = test_files
        self.control.test_files = test_files

        # list dependencies doesnt care about current state of outdated
        if self.list_dependencies or self.graph_dependencies:
            return

        # execute doit to figure out which test modules are outdated
        outdated = self.control.get_outdated()
        # split items into 2 groups to be executed or not
        selected = []
        for colitem in items:
            path = str(colitem.fspath)
            if path in outdated:
                self.outofdate[path].append(colitem.nodeid)
                selected.append(colitem)
            else:
                self.uptodate_paths.add(path)

        # TODO: reorder modules
        items[:] = selected




    # FIXME should use termial to print stuff
    def pytest_runtestloop(self):
        """print up-to-date tests info before running tests or...
        """
        # print info commands
        if not self.run:
            if self.list_outdated:
                self.print_outdated()
            elif self.list_dependencies:
                self.control.print_deps()
            elif self.graph_dependencies:
                print('Graph file written in deps.dot')
                self.control.create_dot_graph()
            return 0 # dont execute tests

        self.print_uptodate_test_files()


    def print_uptodate_test_files(self):
        """print info on up-to-date tests"""
        if self.uptodate_paths:
            print()
        rel_paths = (os.path.relpath(p) for p in self.uptodate_paths)
        for test_file in sorted(rel_paths):
            print("{}  [up-to-date]".format(test_file))

    def print_outdated(self):
        """print list of outdated test files"""
        outdated = []
        for test in self.test_files:
            if test not in self.uptodate_paths:
                outdated.append(test)

        print()
        if outdated:
            print("List of outdated test files:")
            rel_paths = (os.path.relpath(p) for p in outdated)
            for test in sorted(rel_paths):
                print(test)
        else:
            print("All test files are up to date")


    def pytest_runtest_logreport(self, report):
        """save success and failures result so we can decide which files
        should be marked as successful in doit

        py.test hook: called on setup/call/teardown
        """
        if report.failed:
            self.failed.add(report.nodeid)
        else:
            self.passed.add(report.nodeid)

    def pytest_sessionfinish(self, session):
        """save success in doit"""
        if not self.run:
            return

        # if some tests were deselected by a keyword we cant assure all tests
        # passed
        if getattr(session.config.option, 'keyword', None):
            print("\nWARNING: incremental not saving results because -k was used")
            return

        successful = []
        for path in self.test_files:
            for nodeid in self.outofdate[path]:
                if nodeid in self.failed:
                    break
                # check all items were really executed
                # when user hits Ctrl-C sessionfinish still gets called
                if nodeid not in self.passed:
                    break
            else:
                successful.append(path)

        self.control.save_success(os.path.abspath(f) for f in successful)
