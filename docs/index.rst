.. pytest-incremental documentation master file, created by
   sphinx-quickstart on Wed Apr 22 18:47:03 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

===========================================================
pytest-incremental: py.test plugin - incremenal test runner
===========================================================


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

