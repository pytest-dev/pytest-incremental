import os

import pytest_doit
from pytest_doit import find_imports, _PyModule, ModuleSet

SAMPLE = os.path.join(os.path.dirname(__file__), 'sample')
SAMPLE_INIT = os.path.join(SAMPLE, '__init__.py')
SAMPLE_A = os.path.join(SAMPLE, 'sample_a.py')
SAMPLE_B = os.path.join(SAMPLE, 'sample_b.py')
SUBSAMPLE = os.path.join(SAMPLE, 'subsample')
SAMPLE_C = os.path.join(SUBSAMPLE, 'sample_c.py')

def test_find_imports():
    imports = find_imports(SAMPLE_A)
    assert (None, 'os', None, None) == imports[0]
    assert ('sample_b', 'xyz', None, 0) == imports[1]
    assert (None, 'sample_c', None, None) == imports[2]
    assert ('', 'sample_d', None, 2) == imports[3]
    assert ('sample_e', 'jkl', None, 2) == imports[4]
    assert ('sample_f', '*', None, 0) == imports[5]
    assert (None, 'sample_g.other', None, None) == imports[6]
    assert 7 == len(imports)


class Test_ModuleSet(object):

    def test_import_top(self, monkeypatch):
        def mockreturn(path):
            return [(None, 'imp1', None, None),
                    (None, 'imp2', None, None),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet(['imp1.py', 'imp2.py'])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert 'imp1.py' in module.imports
        assert 'imp2.py' in module.imports
        assert 2 == len(module.imports)

    def test_import_not_tracked(self, monkeypatch):
        def mockreturn(path):
            return [(None, 'imp1', None, None),
                    (None, 'imp2', None, None),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet(['imp1.py'])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert 'imp1.py' in module.imports
        assert 1 == len(module.imports)

    def test_from_import_names(self, monkeypatch):
        def mockreturn(path):
            return [('imp1', 'xyz', None, 0),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet(['imp1.py'])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert 'imp1.py' in module.imports
        assert 1 == len(module.imports)

    def test_import_names(self, monkeypatch):
        def mockreturn(path):
            return [(None, 'imp1.xyz', None, None),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet(['imp1.py'])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert 'imp1.py' in module.imports
        assert 1 == len(module.imports)

    def test_import_package(self, monkeypatch):
        def mockreturn(path):
            return [(None, 'sample', None, None),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet([SAMPLE_INIT, SAMPLE_A])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert SAMPLE_INIT in module.imports
        assert 1 == len(module.imports)

    def test_from_package_import(self, monkeypatch):
        def mockreturn(path):
            return [('sample', 'sample_a', None, 0),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet([SAMPLE_INIT, SAMPLE_A])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert SAMPLE_A in module.imports
        assert 1 == len(module.imports)

    def test_from_package_import_name(self, monkeypatch):
        def mockreturn(path):
            return [('sample', 'abc', None, 0),]
        monkeypatch.setattr(pytest_doit, 'find_imports', mockreturn)
        modset = ModuleSet([SAMPLE_INIT, SAMPLE_A])
        module = _PyModule('main.py')
        modset.set_imports(module)
        assert SAMPLE_INIT in module.imports
        assert ['sample','__init__'] == modset.by_path[SAMPLE_INIT].name
        assert 1 == len(module.imports)

    def test_relative_import(self):
        modset = ModuleSet([SAMPLE_INIT, SAMPLE_A])
        module = _PyModule(SAMPLE_B)
        modset.set_imports(module)
        assert SAMPLE_A in module.imports
        assert ['sample','sample_a'] == modset.by_path[SAMPLE_A].name
        assert 1 == len(module.imports)

    def test_intrapkg_import(self):
        modset = ModuleSet([SAMPLE_INIT, SAMPLE_A])
        module = _PyModule(SAMPLE_C)
        modset.set_imports(module)
        assert SAMPLE_A in module.imports
        assert ['sample','sample_a'] == modset.by_path[SAMPLE_A].name
        assert 1 == len(module.imports)

