
import glob

CODE_FILES = glob.glob("pytest_doit.py")
TEST_FILES = glob.glob("tests/test_*.py")


def task_coverage():
    """show coverage for all modules including tests"""
    return {'actions':
                ["coverage run `which py.test` ",
                 ("coverage report --show-missing %s" %
                  " ".join(CODE_FILES + TEST_FILES))
                 ],
            'verbosity': 2}

