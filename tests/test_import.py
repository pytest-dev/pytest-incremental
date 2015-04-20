from __future__ import unicode_literals

import os

from pytest_incremental import find_imports, _PyModule, ModuleSet

# list of modules in sample folder used for testing
sample_dir = os.path.join(os.path.dirname(__file__), 'sample-import')
class FOO:
    pkg = os.path.join(sample_dir, 'foo')
    init = os.path.join(pkg, '__init__.py')
    a = os.path.join(pkg, 'foo_a.py')
    b = os.path.join(pkg, 'foo_b.py')
    c = os.path.join(pkg, 'foo_c.py')
    d = os.path.join(pkg, 'foo_d.py')
    e = os.path.join(pkg, 'foo_e.py')
    f = os.path.join(pkg, 'foo_f.py')
class SUB:
    pkg = os.path.join(FOO.pkg, 'sub')
    init = os.path.join(pkg, '__init__.py')
    a = os.path.join(pkg, 'sub_a.py')
    b = os.path.join(pkg, 'sub_b.py')
BAR = os.path.join(sample_dir, 'bar.py')
BAZ = os.path.join(sample_dir, 'baz.py')



def test_find_imports():
    imports = find_imports(FOO.a)
    # import bar
    assert (None, 'bar', None, None) == imports[0]
    # from foo import foo_b
    assert ('foo', 'foo_b', None, 0) == imports[1]
    # from foo.foo_c import obj_c
    assert ('foo.foo_c', 'obj_c', None, 0) == imports[2]
    # from .. import sample_d
    assert (None, 'sample_d', None, 2) == imports[3]
    # from ..sample_e import jkl
    assert ('sample_e', 'jkl', None, 2) == imports[4]
    # from sample_f import *
    assert ('sample_f', '*', None, 0) == imports[5]
    # import sample_g.other
    assert (None, 'sample_g.other', None, None) == imports[6]
    # TODO test `impors XXX as YYY`
    assert 7 == len(imports)



class Test_PyModule(object):
    def test_repr(self):
        module = _PyModule(SUB.a)
        assert "<_PyModule {}>".format(SUB.a) == repr(module)

    def test_is_pkg(self):
        assert True == _PyModule.is_pkg(FOO.pkg)
        assert False == _PyModule.is_pkg(FOO.init)
        assert False == _PyModule.is_pkg(FOO.a)
        assert True == _PyModule.is_pkg(SUB.pkg)
        assert False == _PyModule.is_pkg(SUB.a)

    def test_fqn(self):
        assert ['bar'] == _PyModule(BAR).fqn
        assert ['foo', '__init__'] == _PyModule(FOO.init).fqn
        assert ['foo', 'foo_a'] == _PyModule(FOO.a).fqn
        assert ['foo', 'sub', 'sub_a'] == _PyModule(SUB.a).fqn


class Test_ModuleSet_Init(object):

    def test_init_with_packge(self):
        modset = ModuleSet([FOO.init, FOO.a])
        assert set(['foo']) == modset.pkgs
        assert 2 == len(modset.by_path)
        assert modset.by_path[FOO.init].fqn == ['foo', '__init__']
        assert modset.by_path[FOO.a].fqn == ['foo', 'foo_a']
        assert 2 == len(modset.by_name)
        assert modset.by_name['foo.__init__'].fqn == ['foo', '__init__']
        assert modset.by_name['foo.foo_a'].fqn == ['foo', 'foo_a']

    def test_init_no_packge(self):
        # if a module of a package is added but no __init__.py
        # its packages is not added to the list of packages
        modset = ModuleSet([FOO.a])
        assert 0 == len(modset.pkgs)
        assert 1 == len(modset.by_path)
        assert modset.by_path[FOO.a].fqn == ['foo', 'foo_a']

    def test_init_subpackge(self):
        modset = ModuleSet([FOO.init, SUB.init, SUB.a])
        assert set(['foo', 'foo.sub']) == modset.pkgs
        assert 3 == len(modset.by_path)
        assert modset.by_path[SUB.a].fqn == ['foo', 'sub', 'sub_a']


class Test_ModuleSet_GetImports(object):

    def test_import_not_tracked(self):
        modset = ModuleSet([FOO.a])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 0

    def test_import_module(self):
        # import bar
        modset = ModuleSet([FOO.a, BAR])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 1
        assert BAR in got

    def test_import_pkg(self):
        # import foo
        modset = ModuleSet([FOO.init, BAR])
        got = modset.get_imports(modset.by_name['bar'])
        assert len(got) == 1
        assert FOO.init in got

    def test_from_pkg_import_module(self):
        # from foo import foo_b
        modset = ModuleSet([FOO.init, FOO.a, FOO.b])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 1
        assert FOO.b in got

    def test_from_import_object(self):
        # from foo.foo_c import obj_c
        modset = ModuleSet([FOO.init, FOO.a, FOO.b, FOO.c])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 2
        assert FOO.b in got # doesnt matter for this test
        assert FOO.c in got

    def test_from_pkg_import_obj(self):
        # from foo import obj_1
        modset = ModuleSet([FOO.init, BAZ])
        got = modset.get_imports(modset.by_name['baz'])
        assert len(got) == 1
        assert FOO.init in got

    def test_import_obj(self):
        # import baz.obj_baz
        modset = ModuleSet([FOO.b, BAZ])
        got = modset.get_imports(modset.by_name['foo.foo_b'])
        assert len(got) == 1
        assert BAZ in got

    def test_relative_import_old(self):
        # import foo_c
        modset = ModuleSet([FOO.init, FOO.b, FOO.c])
        got = modset.get_imports(modset.by_name['foo.foo_b'])
        assert len(got) == 1
        assert FOO.c in got

    def test_relative_intra_import_pkg_obj(self):
        # from . import foo_i
        modset = ModuleSet([FOO.init, FOO.c])
        got = modset.get_imports(modset.by_name['foo.foo_c'])
        assert len(got) == 1
        assert FOO.init in got

    def test_relative_intra_import_module(self):
        # from . import foo_c
        modset = ModuleSet([FOO.init, FOO.c, FOO.d])
        got = modset.get_imports(modset.by_name['foo.foo_d'])
        assert len(got) == 1
        assert FOO.c in got

    def test_relative_parent(self):
        # from .. import foo_d
        modset = ModuleSet([FOO.init, FOO.d, SUB.init, SUB.a])
        got = modset.get_imports(modset.by_name['foo.sub.sub_a'])
        assert len(got) == 1
        assert FOO.d in got

    def test_relative_sub_import_obj(self):
        # from sub.sub_a import obj_sub_a_xxx
        modset = ModuleSet([FOO.init, FOO.e, SUB.init, SUB.a])
        got = modset.get_imports(modset.by_name['foo.foo_e'])
        assert len(got) == 1
        assert SUB.a in got

    def test_relative_sub_import_mod(self):
        # from sub import sub_a
        modset = ModuleSet([FOO.init, FOO.f, SUB.init, SUB.a])
        got = modset.get_imports(modset.by_name['foo.foo_f'])
        assert len(got) == 1
        assert SUB.a in got

    def test_relative_intra_pkg_obj(self):
        # from sub.sub_A import obj_sub_a_xxx
        modset = ModuleSet([FOO.init, SUB.init, SUB.a, SUB.b])
        got = modset.get_imports(modset.by_name['foo.sub.sub_b'])
        assert len(got) == 1
        assert SUB.a in got
