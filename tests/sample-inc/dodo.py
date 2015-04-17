from glob import glob

from pytest_incremental import IncrementalTasks

def task_x():
    src_files = glob("*.py")
    test_files = glob("tt/*.py")
    inc = IncrementalTasks(src_files + test_files, test_files=test_files)
    yield inc.gen_deps()
    yield inc.gen_print_deps()
    yield inc.gen_dep_graph()

