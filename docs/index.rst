.. pytest-incremental documentation master file, created by
   sphinx-quickstart on Wed Apr 22 18:47:03 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

============================================================
pytest-incremental: py.test plugin - incremental test runner
============================================================


Github:
    https://github.com/pytest-dev/pytest-incremental

PyPI:
    https://pypi.python.org/pypi/pytest-incremental



`pytest-incremental` is a `py.test <http://pytest.org/>`_ plug-in.
It analyses your project structure and file modifications between test-runs
to modify the order tests are executed and de-select tests.
This allows a much faster feedback for interactive test execution.

Check the :ref:`documentation <motivation>` for more details.

Note that *py.test* has support to run standard unittest's and nose's tests.
So even if you don't use *py.test* as a test framework you might be able to
use it as a test runner.



Install
=========

pytest-incremental is tested on python  2.7 - 3.3-3.4

``pip install pytest-incremental``



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



