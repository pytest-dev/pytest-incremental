from glob import glob

from pytest_incremental import IncrementalTasks

def task_x():
    inc = IncrementalTasks(glob("*.py"), glob("tt/*.py"))
    yield inc.gen_deps()
    yield inc.gen_print_deps()
    yield inc.gen_dep_graph()

