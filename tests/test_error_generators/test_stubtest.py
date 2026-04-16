import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from stub_adder.transformer.error_generator._stubtest import Stubtest


class TestStubtestResolve(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.stubs_dir = self.tmp / "stubs" / "my-pkg"
        self.pkg_dir = self.stubs_dir / "my_pkg"
        self.pkg_dir.mkdir(parents=True)
        self.init_pyi = self.pkg_dir / "__init__.pyi"
        self.init_pyi.write_text("def foo() -> None: ...\n")
        self.module_pyi = self.pkg_dir / "utils.pyi"
        self.module_pyi.write_text("def bar() -> int: ...\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_resolve_package_init(self):
        result = Stubtest._resolve_pyi("my_pkg.foo", self.stubs_dir)
        self.assertEqual(result, self.init_pyi.resolve())

    def test_resolve_submodule(self):
        result = Stubtest._resolve_pyi("my_pkg.utils.bar", self.stubs_dir)
        self.assertEqual(result, self.module_pyi.resolve())

    def test_resolve_unknown_returns_none(self):
        result = Stubtest._resolve_pyi("unknown.thing", self.stubs_dir)
        self.assertIsNone(result)


class TestStubtestParseErrors(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.stubs_dir = self.tmp / "stubs" / "my-pkg"
        self.pkg_dir = self.stubs_dir / "my_pkg"
        self.pkg_dir.mkdir(parents=True)
        self.init_pyi = self.pkg_dir / "__init__.pyi"
        self.init_pyi.write_text("")
        self.stubtest = Stubtest()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parses_single_error(self):
        output = "error: my_pkg.foo\nStub: ...\nRuntime: ...\n"
        result = self.stubtest._parse_errors(output, self.stubs_dir)
        self.assertIn(self.init_pyi.resolve(), result)
        self.assertEqual(len(result[self.init_pyi.resolve()]), 1)

    def test_parses_multiple_errors(self):
        output = "error: my_pkg.foo\nStub: ...\nerror: my_pkg.bar\nStub: ...\n"
        result = self.stubtest._parse_errors(output, self.stubs_dir)
        self.assertEqual(len(result[self.init_pyi.resolve()]), 2)

    def test_skips_unresolvable(self):
        output = "error: unknown.thing\nStub: ...\n"
        result = self.stubtest._parse_errors(output, self.stubs_dir)
        self.assertEqual(result, {})


class TestStubtestGenerate(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.stubs_dir = self.tmp / "stubs" / "my-pkg"
        self.pkg_dir = self.stubs_dir / "my_pkg"
        self.pkg_dir.mkdir(parents=True)
        self.init_pyi = self.pkg_dir / "__init__.pyi"
        self.init_pyi.write_text("def foo() -> None: ...\n")
        self.stubtest = Stubtest()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_type_is_stubtest(self):
        self.assertEqual(self.stubtest.type, "stubtest")

    def test_venv_path_used_when_set(self):
        """When venv_path is set, run_stubtest_in_venv is called and returns success."""
        venv_dir = self.tmp / "venv"
        venv_dir.mkdir()
        stubtest = Stubtest(venv_path=venv_dir)

        with patch.object(
            Stubtest, Stubtest.run_stubtest_in_venv.__name__, return_value=True
        ):
            result = stubtest.generate([self.init_pyi], self.stubs_dir)
        self.assertEqual(result, {})

    def test_filters_to_layer_files(self):
        """Only errors for pyi_paths in the layer are returned."""
        other = self.pkg_dir / "other.pyi"
        other.write_text("def baz() -> None: ...\n")

        output = (
            "error: my_pkg.foo\nStub: ...\n"
            "error: my_pkg.other.baz\nStub: ...\n"
        )

        venv_dir = self.tmp / "venv"
        venv_dir.mkdir()
        stubtest = Stubtest(venv_path=venv_dir)

        def _fake_run(*args, **kwargs):
            print(output, end="")  # ignore
            return False

        with patch.object(
            Stubtest,
            Stubtest.run_stubtest_in_venv.__name__,
            side_effect=_fake_run,
        ):
            result = stubtest.generate([self.init_pyi], self.stubs_dir)

        self.assertIn(self.init_pyi.resolve(), result)
        self.assertNotIn(other.resolve(), result)
