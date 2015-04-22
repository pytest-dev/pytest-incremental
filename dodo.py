
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
    all_files = " ".join(CODE_FILES + TEST_FILES)
    return {
        'actions': [
            'coverage run `which py.test` {}'.format(all_files),
            "coverage report --show-missing {}".format(all_files),
        ],
        'verbosity': 2,
    }

