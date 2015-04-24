from __future__ import unicode_literals

from pytest_incremental import StringIO, GNode, DepGraph

class Test_GNode(object):
    def test_repr(self):
        node = GNode('foo')
        assert "<GNode(foo)>" == repr(node)

    def test_add_dep(self):
        node = GNode('foo')
        dep1 = GNode('bar1')
        dep2 = GNode('bar2')
        node.add_dep(dep1)
        node.add_dep(dep2)
        assert 2 == len(node.deps)
        assert dep1 in node.deps
        assert dep2 in node.deps

    def test_all_deps(self):
        node = GNode('foo')
        dep1 = GNode('bar1')
        dep2 = GNode('bar2')
        dep3 = GNode('bar3')
        node.add_dep(dep1)
        dep1.add_dep(dep2)
        dep2.add_dep(dep3)
        all_deps = node.all_deps()
        assert 4 == len(all_deps)
        assert node in all_deps
        assert dep1 in all_deps
        assert dep2 in all_deps
        assert dep3 in all_deps


    def test_recursive1(self):
        node = GNode('foo')
        dep1 = GNode('bar1')
        dep2 = GNode('bar2')
        dep3 = GNode('bar3')
        dep4 = GNode('bar4')
        node.add_dep(dep1)
        dep1.add_dep(dep2)
        dep2.add_dep(dep3)
        dep3.add_dep(dep1)
        dep3.add_dep(dep4)

        cycle_deps = set([dep1, dep2, dep3, dep4])
        all_deps = cycle_deps.union(set([node]))
        assert all_deps == node.all_deps()
        assert cycle_deps == dep1.all_deps()
        assert cycle_deps == dep2.all_deps()
        assert cycle_deps == dep3.all_deps()
        assert set([dep4]) == dep4.all_deps()


    def test_recursive2(self):
        n1 = GNode('bar1')
        n2 = GNode('bar2')
        n3 = GNode('bar3')
        n4 = GNode('bar4')
        n5 = GNode('bar5')
        n1.add_dep(n2)
        n2.add_dep(n3)
        n3.add_dep(n4)
        n4.add_dep(n5)
        n5.add_dep(n1)
        n4.add_dep(n2)
        n2.add_dep(n4)

        cycle_deps = set([n1, n2, n3, n4, n5])
        assert n1.all_deps() == cycle_deps
        assert n2.all_deps() == cycle_deps
        assert n3.all_deps() == cycle_deps
        assert n4.all_deps() == cycle_deps

    def test_recursive3(self):
        n1 = GNode('bar1')
        n2 = GNode('bar2')
        n3 = GNode('bar3')
        n1.add_dep(n2)
        n2.add_dep(n3)
        n3.add_dep(n2)

        assert n3.all_deps() == set([n2, n3])
        assert n2.all_deps() == set([n2, n3])
        assert n1.all_deps() == set([n1, n2, n3])



class Test_DepGraph(object):
    graph = DepGraph({
        'a': ['b', 'c'],
        'b': ['d'],
        'd': ['c', 'e'],
    })

    def test_nodes(self):
        b_deps = [n.name for n in self.graph.nodes['b'].all_deps()]
        assert set(b_deps) == set(['c', 'e', 'b', 'd'])

    def test_dot(self):
        output = StringIO()
        self.graph.write_dot(output)
        lines = output.getvalue().splitlines()
        assert '"a" -> "c"' in lines
        assert '"a" -> "b"' in lines
        assert '"b" -> "d"' in lines
        assert '"d" -> "c"' in lines
        assert '"d" -> "e"' in lines


    def test_topsort(self):
        graph = DepGraph({
            'a': ['c'],
            'b': [],
            'c': ['b'],
        })
        assert ['b', 'c', 'a'] == graph.topsort()
