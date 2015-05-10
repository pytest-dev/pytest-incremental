
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


How *pytest-incremental* compares to `testmon <https://github.com/tarpas/testmon>`_ ?
======================================================================================

Both projects have a similar goal but have completely different implementations.
*testmon* uses *coverage.py* to trace the execution of tests while *pytest-incremental* analyses the imported dependencies.

- *testmon* can track sub-module dependencies, so it can de-select more
  tests that *pytest-incremental*
- *testmon* does not re-order tests according to the source structure
- because *testmon* traces the code execution the test execution is slower
  than normally


