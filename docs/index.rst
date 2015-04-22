.. pytest-incremental documentation master file, created by
   sphinx-quickstart on Wed Apr 22 18:47:03 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

===========================================================
pytest-incremental: py.test plugin - incremenal test runner
===========================================================


Github - https://github.com/pytest-dev/pytest-incremental

PyPI - https://pypi.python.org/pypi/pytest-incremental


What is an "incremental test runner" ?
=======================================

The idea is to execute your tests faster by executing not all of them
but only the "required" ones.

When talking about build-tools it is common to refer to the terms:

* initial (full) build - all files are compiled
* incremental build (or partial rebuild) - just changed files are compiled
* no-op build - no files are compiled (none changed since last execution)

So an "incremental test runner" will only re-execute tests that were affected
by changes in the source code since last successful execution.


Install
=========

pytest-incremental is tested on python  2.7 - 3.3-3.4

``pip install pytest-incremental``

``python setup.py install``

local installation
--------------------

You can also just grab the plug-in
`module <https://raw.githubusercontent.com/pytest-dev/pytest-incremental/master/pytest_incremental.py>`_
file and put in your project path. Install the dependencies.
Then enable it (check `pytest docs <http://pytest.org/latest/plugins.html#conftest-py-local-per-directory-plugins>`_).


Usage
======

Just pass the parameter ``--inc`` when calling from the command line::

  $ py.test --inc


You can also enable it by default adding the following
line to your ``pytest.ini``::

  [pytest]
  addopts = --inc


watched packages
------------------

By default all modules from within your *CWD* will be counted as dependencies
if imported. In order to limit or extend the watched folders you must use
the parameter ``--inc-path``


This can be used in case you want to watch for changes in modules that are
in another project.
For example if you are testing ``my_lib`` and want to check for changes
in dependencies from your `py3rd` package::

$ py.test --inc --inc-path my_lib --inc-path ../py3rd-trunk/py3rd


dependencies
--------------

You can check what are the actual dependencies detected by running the command::

 $ py.test --inc-deps

for better visualization you can create a graph file in "dot" format
(see `graphviz <http://www.graphviz.org/>`_ )::

 $ py.test --inc-graph

To generate an image::

 $ py.test --inc-graph-image


You can also check what are the outdated tests without executing them::

 $ py.test --inc-outdated



How it works ?
================

`pytest-incremental` is a `pytest <http://pytest.org/>`_ plug-in.
So if you can run your test suite with pytest you can use `pytest-incremental`.

Note that pytest has support to run standard unittest's and nose's tests.
So even if you don't use pytest as a test framework you might be able to
use it as a test runner.

The plug-in will analyze your python source files and through its imports
define the dependencies of the modules.
`doit <http://pydoit.org>`_ is used to keep track of
the dependencies and save results.
The plug-in will modify how pytest collect your tests.
pytest do the rest of the job of actually running the tests and
reporting the results.


Limitations
==============

``pytest-incremental`` looks for imports recursively to find dependencies (using
AST). But given the very dynamic nature of python there are still some cases
that a module can be affected by a module that are not detected.

* `from package import *` modules imported from __all__ in a package are not
  counted as a dependency
* modules imported not using the *import* statement
* modules not explicitly imported but used at run-time (i.e. conftest.py when
  running your tests with pytest)
* monkey-patching. (i.e. A imports X.  B monkey-patches X. In this case A might
  depend on B)
* others ?


