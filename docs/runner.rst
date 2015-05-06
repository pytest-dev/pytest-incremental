
.. _motivation:

Test Runners
============

Let's start by looking at what is a test-runner.
We need to differentiate a **test-runner** from a **test-framework**.

From python `documentation <https://docs.python.org/3/library/unittest.html>`_:
A test runner is a component which orchestrates the execution of tests and
provides the outcome to the user. The runner may use a graphical interface, a
textual interface, or return a special value to indicate the results of
executing the tests.

A test-framework defines an API that is used to write the tests.
For example the `unittest` module from python's stdlib.

The `unittest` module also defines an API for creating test runners, and
provides a basic test runner `implementation <https://docs.python.org/3/library/unittest.html#unittest.TextTestRunner>`_.
Apart from this, there are other runners that has support for running
`unittest`\'s tests like `nose` and `py.test`.

On the other hand `py.test` defines its own test-framework but only
its own runner is capable of running its tests.


Test Runner Features
====================

When using a test runner interactively in the command line I expect two
main things:

- fast feedback: I want to know as fast as possible if my latest changes are
  OK (tests are executed successfully or not).
- in case of test failures, how easy it is to find the problem.

Note that I said **fast feedback** not faster **tests**.
Of course the actual test
(and not the test runner) plays the main role in the time to execute a test.
But you should not always need to wait until **all** tests are executed before
getting some feedback.

For example *py.test* offers the option `-x/--exitfirst` and `--maxfail`,
to display information on failures without waiting for all tests to finish.
Also check the `instafail plugin <https://github.com/pytest-dev/pytest-instafail>`_.

Another way to achieve faster feedback is by executing just a sub-set of
your tests.
Using *py.test*, apart from selecting tests from just a package or module,
also has a very powerful system to select tests based
on *keywords* using the option `-k`.
While this feature is extremely useful it

*py.test* has great tools to help you debug failed tests like colorful output,
*pdb* integration, assertion re-write and control of traceback verbosity.


Importance of Test Ordering
===========================

By default *py.test* will execute tests grouped by test module.
Modules are ordered alphabetically, tests from each module are executed
in the order they are defined.
Although unit-tests *should* work when executed in any order,
it is important to execute them in a defined order so failures can be easily
reproduced.

But using a simple alphabetical order that does not take into account
the structure of the code has several disadvantages.

#. To achieve faster feedback it is important that the most **relevant** tests
   should be executed first. Using alphabetical order you might spend a long
   time executing tests that were not affected by recent changes, or execute
   tests that have little chance to fail.

#. It is common that a single change break several tests.
   In order to easily identify the cause of the problem it is important to
   look at the test that is directly testing the point where the code changed.
   It might not be easy to pin-point the problem when looking at failures
   in tests that were broken but not directly test the problem.
   Executing the most **relevant** tests first you could make sure to get
   *direct* failures first.


How to order tests
==================

There are two main factors to determine a most relevant order to execute tests.

- The source code inter-dependency structure
  (this is done by analyzing the *imports*)

- Modified modules since last successful execution


Lets look at simple example project that contains four modules,
and each module a corresponding test module.
Look at the **imports** graph below where an edge ``bar -> util``
means that ``bar.py`` imports ``util.py``.

.. graphviz::

  digraph imports {
   rankdir = BT
   util [shape=box, color=blue]
   bar [shape=box, color=blue]
   foo [shape=box, color=blue]
   app [shape=box, color=blue]

   "bar" -> "util"
   "foo" -> "util"
   "app" -> "bar"
   "app" -> "foo"

   "test_util" -> "util"
   "test_bar" -> "bar"
   "test_foo" -> "foo"
   "test_app" -> "app"
  }



Initial (full) run
------------------

On the first run all tests must be executed.
Since ``bar`` and ``foo`` depends on ``util``, we want to execute
``test_util`` first to make sure any problems on ``util`` are caught
first by its direct tests on ``test_util``.

The same applies for ``app`` in relation to ``foo`` and ``bar``.
``foo`` and ``bar`` both have the same *level* in the structure,
so they are just ordered in alphabetically.

So we execute tests in the following order::

  test_util, test_bar, test_foo, test_app


incremental run - test modified
-------------------------------

Now let's say that we modify the file ``test_foo``.
We know that all tests were OK before this modification,
so the most relevant tests to be execute are on ``test_foo`` itself.

Not only ``test_foo`` should be executed first, all other tests
do not need to be executed at all because a change in ``test_foo``
does not affect any other tests since no other module
depends (imports) ``test_foo``.

.. graphviz::

  digraph imports {
   rankdir = BT
   util [shape=box, color=blue]
   bar [shape=box, color=blue]
   foo [shape=box, color=blue]
   app [shape=box, color=blue]

   "bar" -> "util"
   "foo" -> "util"
   "app" -> "bar"
   "app" -> "foo"

   "test_util" -> "util"
   "test_bar" -> "bar"
   "test_foo" -> "foo"
   "test_app" -> "app"

   test_foo [color=red, fontcolor=red, style=filled, fillcolor=yellow]
  }


The same behavior can be observed for a change in any other test module
in this example.
Since there are not dependencies between test modules, a change in a test
module will require the execution only of the modified module.


incremental run - source modified
---------------------------------

Let's check now what happens when ``foo`` is modified.
Looking at the graph it is easy to see which tests are going to
be affected.

.. graphviz::

  digraph imports {
   rankdir = BT
   util [shape=box, color=blue]
   bar [shape=box, color=blue]
   foo [shape=box, color=blue]
   app [shape=box, color=blue]

   "bar" -> "util"
   "foo" -> "util"
   "app" -> "bar"
   "app" -> "foo" [color=red]

   "test_util" -> "util"
   "test_bar" -> "bar"
   "test_foo" -> "foo" [color=red]
   "test_app" -> "app" [color=red]

   foo [fontcolor=red, color=red]
   app [color=red]
   test_foo [color=red, style=filled, fillcolor=yellow]
   test_app [color=red, style=filled, fillcolor=yellow]
  }

The order of test execution is ``test_foo`` then ``test_app``.
Other tests are not executed at all.

Analyzing the graph is easy to see that a change in ``app`` would cause only
``test_app`` to be execute. And a change in ``util`` would cause all tests
to be executed.




pytest-incremental
==================

Hopefully by now it is clear that by taking in account the structure of the
code to order the tests, the test-runner can:

- reduce total execution time for incremental changes
- get faster feedback by executing first the tests which have direct code
  under test changes
- easier to debug test failures because of more relevant test ordering

``pytest-incremental`` is a *py.test* plugin that analyses the source
code and changes between runs to re-order and de-select tests cases.


caveats
=======

``pytest-incremental`` looks for imports recursively to find dependencies (using
AST). But given the very dynamic nature of python there are still some cases
that a module can be affected by a module that are not detected.

* modules imported not using the *import* statement
* modules not explicitly imported but used at run-time
* monkey-patching. (i.e. A imports X.  B monkey-patches X. In this case A might
  depend on B)
* others ?


cyclic dependencies
-------------------

If your project has dependency cycles will negatively affect the efficacy
of *pytest-incremental*.
Dependency cycles are bad not only for *pytest-incremental*, it makes the code
hard to understand and modify. *pytest-incremental* does not try to be smart
handling it, so you better **fix** your code and remove the cycles!

.. graphviz::

  digraph imports {
   rankdir = BT
   util [shape=box, color=blue]
   bar [shape=box, color=blue]
   foo [shape=box, color=blue]
   app [shape=box, color=blue]

   "bar" -> "util"
   "foo" -> "util"
   "app" -> "bar"
   "app" -> "foo"
   "util" -> "app"
   "bar" -> "app"
  }

When you have cycles any change end up affecting all modules!
