================
README
================


pytest-incremental
====================

an incremental test runner (pytest plug-in)


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


Install
=========

pytest-incremental is tested on python 2.6, 2.7.

``pip install pytest-incremental```

``python setup.py install``

local installation
--------------------

You can also just grab the plug-in
`module <https://bitbucket.org/schettino72/pytest-incremental/src/tip/pytest_incremental.py>`_
file and put in your project path.
Then enable it (check `pytest docs <http://pytest.org/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file>`_).


Usage
======

Just pass the parameter ``--incremental`` when calling from the command line::

  $ py.test --incremental


You can also enable it by default adding the following
line to your ``pytest.ini``::

  [pytest]
  addopts = --incremental


watched packages
------------------

By default all modules collected by py.test will be used as dependencies
if imported. In order to limit or extend the watched folders you must use
the parameter ``--watch-path``


This can be used in case you want to watch for changes in modules that are
in another project.
For example if you are testing ``my_lib`` and want to check for changes
in dependencies from your `py3rd` package::

$ py.test --incremental --watch-pkg my_lib --watch-pkg ../py3rd-trunk/py3rd


Note: If you want to execute tests from a single file like::

  $ py.test  tests/test_foo.py

It is required to use ``--watch-path`` because the source files will not
be collected by py.test

You should call::

  $ py.test --incremental --watch-pkg my_lib tests/test_foo.py


dependencies
--------------

You can check what are the actual dependencies detected by running the command::

 $ py.test --list-dependencies

for better visualization you can create a graph file in "dot" format
(see `graphviz <http://www.graphviz.org/>`_ ::

 $ py.test --graph-dependencies
 $ dot -Tpng -o imports.png imports.dot


You can also check what are the outdated tests without executing them::

 $ py.test --list-outdated



Limitations
==============

``pytest-incremental`` looks for imports recursively to find dependencies (using AST). But given the very dynamic nature of python there are still some cases that a module can be affected by a module that are not detected.

 * `from package import *` modules imported from __all__ in a package are not counted as a dependency
 * modules imported not using the *import* statement
 * modules not explicitly imported but used at run-time (i.e. conftest.py when running your tests with pytest)
 * monkey-patching. (i.e. A imports X.  B monkey-patches X. In this case A might depend on B)
 * others ?


Project Details
===============

 - Project code + issue track on `github <https://github.com/pytest-dev/pytest-incremental>`_
 - `Discussion group <http://groups.google.co.in/group/python-doit>`_