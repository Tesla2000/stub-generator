import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_added._stub_tuple import _StubTuple
from stub_added.transformer.fill_with_llm._topo import build_module_map
from stub_added.transformer.fill_with_llm._topo import find_cycle
from stub_added.transformer.fill_with_llm._topo import internal_imports
from stub_added.transformer.fill_with_llm._topo import pyi_to_deps
from stub_added.transformer.fill_with_llm._topo import topo_layers


def _make_stubs(tmp_path: Path, files: dict[str, str]) -> list[_StubTuple]:
    stubs: list[_StubTuple] = []
    for rel, src in files.items():
        py = tmp_path / rel
        py.parent.mkdir(parents=True, exist_ok=True)
        py.write_text(textwrap.dedent(src))
        pyi = py.with_suffix(".pyi")
        pyi.write_text("")
        stubs.append(_StubTuple(py_path=py, pyi_path=pyi))
    return stubs


class TestBuildModuleMap(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_simple_modules(self) -> None:
        stubs = _make_stubs(self.tmp_path, {"pkg/a.py": "", "pkg/b.py": ""})
        mapping = build_module_map(stubs)
        self.assertEqual(set(mapping), {"pkg.a", "pkg.b"})

    def test_init_strips_dunder(self):
        stubs = _make_stubs(
            self.tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""}
        )
        mapping = build_module_map(stubs)
        self.assertIn("pkg", mapping)
        self.assertIn("pkg.a", mapping)

    def test_single_file(self):
        stubs = _make_stubs(self.tmp_path, {"mymod.py": ""})
        mapping = build_module_map(stubs)
        self.assertEqual(len(mapping), 1)
        self.assertTrue(list(mapping)[0].endswith("mymod"))


class TestInternalImports(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_detects_import(self):
        stubs = _make_stubs(
            self.tmp_path, {"pkg/a.py": "import pkg.b", "pkg/b.py": ""}
        )
        module_map = build_module_map(stubs)
        deps = internal_imports(self.tmp_path / "pkg/a.py", module_map)
        self.assertEqual(deps, {"pkg.b"})

    def test_detects_from_import(self):
        stubs = _make_stubs(
            self.tmp_path, {"pkg/a.py": "from pkg import b", "pkg/b.py": ""}
        )
        module_map = build_module_map(stubs)
        deps = internal_imports(self.tmp_path / "pkg/a.py", module_map)
        self.assertEqual(deps, {"pkg.b"})

    def test_ignores_external_imports(self):
        stubs = _make_stubs(
            self.tmp_path, {"pkg/a.py": "import os\nimport sys"}
        )
        module_map = build_module_map(stubs)
        deps = internal_imports(self.tmp_path / "pkg/a.py", module_map)
        self.assertEqual(deps, set())


class TestPyiToDeps(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty(self):
        self.assertEqual(pyi_to_deps([]), {})

    def test_transitive_not_included(self):
        stubs = _make_stubs(
            self.tmp_path,
            {
                "pkg/a.py": "from pkg import b",
                "pkg/b.py": "from pkg import c",
                "pkg/c.py": "",
            },
        )
        deps = pyi_to_deps(stubs)
        a_pyi = self.tmp_path / "pkg/a.pyi"
        b_pyi = self.tmp_path / "pkg/b.pyi"
        c_pyi = self.tmp_path / "pkg/c.pyi"
        self.assertEqual(deps[a_pyi], {b_pyi})
        self.assertEqual(deps[b_pyi], {c_pyi})
        self.assertEqual(deps[c_pyi], set())


class TestTopoLayers(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty(self):
        self.assertEqual(topo_layers([]), [])

    def test_independent_files_one_layer(self):
        stubs = _make_stubs(self.tmp_path, {"pkg/a.py": "", "pkg/b.py": ""})
        layers = topo_layers(stubs)
        self.assertEqual(len(layers), 1)
        self.assertEqual(len(layers[0]), 2)

    def test_linear_chain_ordered(self):
        stubs = _make_stubs(
            self.tmp_path,
            {
                "pkg/a.py": "from pkg import b",
                "pkg/b.py": "from pkg import c",
                "pkg/c.py": "",
            },
        )
        layers = topo_layers(stubs)
        self.assertEqual(len(layers), 3)
        pyi_names = [[s.pyi_path.stem for s in layer] for layer in layers]
        self.assertEqual(pyi_names[0], ["c"])
        self.assertEqual(pyi_names[1], ["b"])
        self.assertEqual(pyi_names[2], ["a"])

    def test_cycle_does_not_hang(self):
        stubs = _make_stubs(
            self.tmp_path,
            {"pkg/a.py": "from pkg import b", "pkg/b.py": "from pkg import a"},
        )
        layers = topo_layers(stubs)
        all_stubs = [s for layer in layers for s in layer]
        self.assertEqual(len(all_stubs), 2)


class TestFindCycle(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_simple_cycle(self):
        a = self.tmp_path / "a.pyi"
        b = self.tmp_path / "b.pyi"
        remaining_path: dict[Path, set[str]] = {a: {"mod.b"}, b: {"mod.a"}}
        mod_to_path = {"mod.a": a, "mod.b": b}
        cycle = find_cycle(remaining_path, mod_to_path)
        self.assertGreaterEqual(len(cycle), 2)
        self.assertTrue(set(cycle).issubset({a, b}))
