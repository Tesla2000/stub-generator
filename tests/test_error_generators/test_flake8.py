import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from stub_adder.transformer.error_generator._flake8 import Flake8, Flake8Config


class TestFlake8Generate(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.flake8 = Flake8()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _mock_run(self, stdout: str, returncode: int):
        mock = MagicMock()
        mock.stdout = stdout
        mock.returncode = returncode
        return mock

    def test_no_errors_returns_empty(self):
        pyi = self.tmp / "clean.pyi"
        pyi.write_text("def foo(x: int) -> str: ...\n")
        with patch(
            "subprocess.run", return_value=self._mock_run("", returncode=0)
        ):
            result = self.flake8.generate([pyi], self.tmp)
        self.assertEqual(result, {})

    def test_error_for_known_file_returned(self):
        pyi = self.tmp / "bad.pyi"
        pyi.write_text("import os\n")
        line = f"{pyi}:1:1: F401 'os' imported but unused"
        with patch(
            "subprocess.run", return_value=self._mock_run(line, returncode=1)
        ):
            result = self.flake8.generate([pyi], self.tmp)
        self.assertIn(pyi, result)
        self.assertEqual(len(result[pyi]), 1)
        self.assertIn("F401", result[pyi][0])

    def test_error_for_unknown_file_excluded(self):
        pyi = self.tmp / "known.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        other = (self.tmp / "other.pyi").resolve()
        line = f"{other}:1:1: F401 'os' imported but unused"
        with patch(
            "subprocess.run", return_value=self._mock_run(line, returncode=1)
        ):
            result = self.flake8.generate([pyi], self.tmp)
        self.assertEqual(result, {})

    def test_multiple_errors_same_file(self):
        pyi = self.tmp / "multi.pyi"
        pyi.write_text("import os\nimport sys\n")
        lines = (
            f"{pyi}:1:1: F401 'os' imported but unused\n"
            f"{pyi}:2:1: F401 'sys' imported but unused"
        )
        with patch(
            "subprocess.run", return_value=self._mock_run(lines, returncode=1)
        ):
            result = self.flake8.generate([pyi], self.tmp)
        self.assertIn(pyi, result)
        self.assertEqual(len(result[pyi]), 2)

    def test_type_is_flake8(self):
        self.assertEqual(self.flake8.type, "flake8")


class TestFlake8Config(TestCase):
    def test_default_selects_only_y_rules(self):
        self.assertEqual(Flake8Config().select, ("Y",))

    def test_default_ignores_y090_y091(self):
        cfg = Flake8Config()
        self.assertIn("Y090", cfg.extend_ignore)
        self.assertIn("Y091", cfg.extend_ignore)

    def test_custom_select(self):
        cfg = Flake8Config(select=("E", "W"))
        self.assertEqual(cfg.select, ("E", "W"))

    def test_select_passed_to_command(self):
        pyi_path = Path("/tmp/test.pyi")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = MagicMock()
            m.stdout = ""
            m.returncode = 0
            return m

        flake8 = Flake8(config=Flake8Config(select=("E",), extend_ignore=()))
        with patch("subprocess.run", side_effect=fake_run):
            flake8.generate([pyi_path], Path("/tmp"))

        self.assertTrue(any("--select=E" in arg for arg in captured["cmd"]))

    def test_extend_ignore_passed_to_command(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = MagicMock()
            m.stdout = ""
            m.returncode = 0
            return m

        flake8 = Flake8()
        with patch("subprocess.run", side_effect=fake_run):
            flake8.generate([Path("/tmp/test.pyi")], Path("/tmp"))

        self.assertTrue(any("Y090" in arg for arg in captured["cmd"]))


class TestFlake8Integration(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_detects_docstring_y021(self):
        pyi = self.tmp / "doc.pyi"
        pyi.write_text('class Foo:\n    """A docstring."""\n    x: int\n')
        result = Flake8().generate([pyi], self.tmp)
        self.assertIn(pyi, result)
        self.assertTrue(any("Y021" in e for e in result[pyi]))

    def test_clean_file_no_errors(self):
        pyi = self.tmp / "clean.pyi"
        pyi.write_text("def foo(x: int) -> str: ...\n")
        result = Flake8().generate([pyi], self.tmp)
        self.assertEqual(result, {})
