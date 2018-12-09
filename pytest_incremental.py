"""
pytest-incremental : an incremental test runner (pytest plugin)
https://pypi.python.org/pypi/pytest-incremental

The MIT License - see LICENSE file
Copyright (c) 2011-2018 Eduardo Naufel Schettino
"""

__version__ = (0, 5, 0)

import os
import json
import functools
from collections import defaultdict
from io import StringIO

from import_deps import ModuleSet, PyModule
from doit.task import Task, DelayedLoader
from doit.cmd_base import ModuleTaskLoader
from doit.cmd_run import Run
from doit.reporter import ZeroReporter
from doit import doit_cmd
from doit.tools import config_changed


######### Graph implementation

class GNode(object):
    '''represents a node in a direct graph

    Designed to return a list of all nodes in a sub-graph.
    The sub-graph from each node is built on demand and cached after built.
    '''
    def __init__(self, name):
        self.name = name
        self.deps = set() # of direct GNode deps
        self.implicit_deps = []
        # all_deps are lazily calculated and cached
        self._all_deps = None # set of all (recursive) deps names

    def __repr__(self):
        return "<GNode({})>".format(self.name)

    def add_dep(self, dep):
        """add a dependency of self"""
        self.deps.add(dep)

    def all_deps(self):
        """return set of GNode with all deps from this node (including self)"""
        if self._all_deps is not None:
            return self._all_deps
        todo = set()
        done = set()
        todo.add(self)
        while todo:
            node = todo.pop()
            if node._all_deps:
                done.update(node._all_deps)
            else:
                todo.update(n for n in node.deps if n not in done)
                done.add(node)
        done.update(self.implicit_deps)
        self._all_deps = done
        return done


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
        stream.write("digraph imports {\nrankdir = BT\n")
        for node in sorted(self.nodes.values(), key=lambda x:x.name):
            # FIXME add option to include test files or not
            #if node.name.startswith('test'):
            #    continue
            node_path = os.path.relpath(node.name)
            if node.deps:
                for dep in sorted(node.deps, key=lambda x: x.name):
                    dep_path = os.path.relpath(dep.name)
                    stream.write('"{}" -> "{}"\n'.format(node_path, dep_path))
            else:
                stream.write('"{}"\n'.format(node_path))
        stream.write("}\n")


    def topsort(self):
        '''return list of node names in topological order

        If A has deps [B, C]. We say that A is a target, B and C are sources
        '''
        num_src = {}
        targets = defaultdict(list)
        for target in self.nodes.values():
            num_src[target.name] = len(target.deps)
            for source in target.deps:
                targets[source.name].append(target.name)

        result = []
        next_level = [n for n in num_src if num_src[n]==0]

        # each iteration is get all nodes from a level
        while len(result) != len(self.nodes):
            # if there is a cycle all nodes have one or more srcs
            if not next_level:
                lowest = None
                for node_name, srcs in num_src.items():
                    if lowest is None or srcs < lowest:
                        lowest = srcs
                        next_level = [node_name]
                    elif srcs == lowest:
                        next_level.append(node_name)

            # remove elements from num_src so they are not taken account
            # when removing a cycle.
            for n in next_level:
                del num_src[n]

            # sort nodes of this level
            result.extend(sorted(next_level))

            # process nodes preparing for next level
            level = next_level
            next_level = []
            for n in level:
                for target in targets[n]:
                    try:
                        num_src[target] -= 1
                    # cycle might already have remove target
                    except KeyError:
                        continue
                    if num_src[target] == 0:
                        next_level.append(target)
        return result



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


    def create_graph(self):
        """create Graph from json file"""
        with open(self.json_file) as fp:
            deps = json.load(fp)
        return DepGraph(deps)


    @property
    def graph(self):
        """cache graph object"""
        if self._graph is None:
            self._graph = self.create_graph()
        return self._graph


    def action_get_dep(self, module_path):
        """action: return list of direct imports from a single py module

        :return dict: single value 'imports', value set of str file paths
        """
        mod = self.py_mods.by_path[module_path]
        return {'imports': list(str(s) for s in self.py_mods.get_imports(mod))}


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


    @gen_after(name='dep-dot', after_task='dep-json')
    def gen_dep_graph_dot(self, dot_file='deps.dot'):
        """generate tasks for creating a `dot` graph of module imports"""
        yield {
            'basename': 'dep-dot',
            'actions': [(self.action_write_dot, ['deps.dot', self.graph])],
            'file_dep': [self.json_file],
            'targets': [dot_file],
        }

    @gen_after(name='dep-image', after_task='dep-json')
    def gen_dep_graph_image(self, dot_file='deps.dot', img_file='deps.svg'):
        # generate SVG with bottom-up tree
        dot_cmd = 'dot -Tsvg '
        yield {
            'basename': 'dep-image',
            'actions': [dot_cmd + " -o %(targets)s %(dependencies)s"],
            'file_dep': [dot_file],
            'targets': [img_file],
        }




class IncrementalTasks(PyTasks):
    """Manage creation of all tasks for pytest-incremental plugin"""

    def __init__(self, pyfiles, test_files=None, **kwargs):
        PyTasks.__init__(self, pyfiles, **kwargs)
        self.test_files = test_files

    def create_graph(self):
        """overwrite to add implicit dep to conftest file"""
        graph = super(IncrementalTasks, self).create_graph()
        conftest = [mod for mod in graph.nodes.keys()
                    if mod.endswith('conftest.py')]
        for conf in conftest:
            conftest_node = graph.nodes[conf]
            base_dir = os.path.dirname(conf)
            for path, node in graph.nodes.items():
                if path.startswith(base_dir) and path != conf:
                    node.implicit_deps.append(conftest_node)
        return graph

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
        yield self.gen_dep_graph_dot()
        yield self.gen_dep_graph_image()
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
        self.outstream.write(outdated_info)


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
                if get_sub_folders or PyModule.is_pkg(sub_path):
                    this_modules.extend(self._get_pkg_modules(sub_path))
        return this_modules

    def _run_doit(self, sel_tasks, reporter=None, doit_vars=None):
        """load this file as dodo file to collect tasks"""
        inc = IncrementalTasks(self.py_files, test_files=list(self.test_files))
        output = StringIO()
        config = {
            'dep_file': self.DB_FILE,
            'continue': True,
            'outfile': output,
        }
        if reporter:
            config['reporter'] = reporter

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
        return inc.graph, output.read()


    def get_outdated(self):
        """run doit to find out which test files are "outdated"
        A test file is outdated if there was a change in the content in any
        import (direct or indirect) since last succesful execution

        :return set(str): list of outdated files
        """
        outdated_tasks = ['outdated']
        graph, output_str = self._run_doit(outdated_tasks,
                                           reporter=OutdatedReporter)
        outdated_list = json.loads(output_str)
        # dict of outdated with position
        outdated = {}
        order = {p:i for i,p in enumerate(graph.topsort())}
        for test in outdated_list:
            outdated[test] = order[test]
        return outdated

    def save_success(self, success):
        """mark doit test tasks as sucessful"""
        tasks = ['dep-json']
        for path in success:
            tasks.append("outdated:%s" % path)
        self._run_doit(tasks, doit_vars={'success':True})


    def print_deps(self):
        """print list of all python modules being tracked and its dependencies"""
        self._run_doit(['print-deps'])

    def create_dot_graph(self, graph_type='dot'):
        """create a graph of imports in dot format
        """
        tasks = ['dep-dot', 'dep-image'] if graph_type=='image' else ['dep-dot']
        self._run_doit(tasks)



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
        '--inc-graph', action="store_const", const='dot',
        dest="graph_dependencies", default=None,
        help="create graph file of dependencies in dot format 'deps.dot'")
    group.addoption(
        '--inc-graph-image', action="store_const", const='image',
        dest="graph_dependencies", default=None,
        help="create graph file of dependencies in SVG format 'deps.svg'")


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
        self.graph_dependencies = None
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
        pkg_folders = [os.path.abspath(p) for p in
                       session.config.option.watch_path]
        if not pkg_folders:
            pkg_folders = [os.getcwd()]

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
        # dict test_moodule path: relative order position
        outdated = self.control.get_outdated()

        # split items into 2 groups to be executed or not
        item_by_mod = defaultdict(list)
        deselected = []
        for colitem in items:
            path = str(colitem.fspath)
            if path in outdated:
                self.outofdate[path].append(colitem.nodeid)
                item_by_mod[path].append(colitem)
            else:
                self.uptodate_paths.add(path)
                deselected.append(colitem)

        selected = []
        for path, _ in sorted(outdated.items(), key=lambda x: x[1]):
            selected.extend(item_by_mod[path])
        items[:] = selected

        # include number of tests deselected in report footer
        if deselected:
            config.hook.pytest_deselected(items=deselected)




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
                self.control.create_dot_graph(self.graph_dependencies)
                print('Graph dot file written in deps.dot')
                if self.graph_dependencies == 'image':
                    print('Graph image file written in deps.svg')
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
