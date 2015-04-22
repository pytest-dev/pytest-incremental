
import glob

from doitpy.pyflakes import Pyflakes


DOIT_CONFIG = {'default_tasks': ['pyflakes',]}


def task_pyflakes():
    flakes = Pyflakes()
    yield flakes.tasks('*.py')
    yield flakes.tasks('tests/*.py')



CODE_FILES = glob.glob("pytest_incremental.py")
TEST_FILES = glob.glob("tests/test_*.py")

def task_coverage():
    """show coverage for all modules including tests"""
    return {
        'actions': [
            "coverage run `which py.test` ",
            ("coverage report --show-missing %s" %
             " ".join(CODE_FILES + TEST_FILES)),
        ],
        'verbosity': 2,
    }

