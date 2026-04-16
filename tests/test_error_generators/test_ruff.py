import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from stub_adder.transformer.error_generator._ruff import Ruff


def _make_ruff_output(diagnostics: list[dict]) -> str:
    return json.dumps(diagnostics)


class TestRuffGenerate(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.ruff = Ruff()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _mock_run(self, diagnostics: list[dict], returncode: int = 0):
        mock = MagicMock()
        mock.stdout = _make_ruff_output(diagnostics)
        mock.returncode = returncode
        return mock

    def test_no_errors_returns_empty(self):
        pyi = self.tmp / "clean.pyi"
        pyi.write_text("def foo(x: int) -> str: ...\n")
        with patch("subprocess.run", return_value=self._mock_run([])):
            result = self.ruff.generate([pyi], self.tmp)
        self.assertEqual(result, {})

    def test_error_for_known_file_returned(self):
        pyi = (self.tmp / "bad.pyi").resolve()
        pyi.write_text("import os\n")
        diagnostics = [
            {
                "filename": str(pyi),
                "code": "F401",
                "message": "'os' imported but unused",
                "location": {"row": 1, "column": 1},
            }
        ]
        with patch(
            "subprocess.run",
            return_value=self._mock_run(diagnostics, returncode=1),
        ):
            result = self.ruff.generate([pyi], self.tmp)
        self.assertIn(pyi, result)
        self.assertIn("F401", result[pyi][0])

    def test_error_for_unknown_file_excluded(self):
        pyi = self.tmp / "known.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        other = self.tmp / "other.pyi"
        diagnostics = [
            {
                "filename": str(other),
                "code": "F401",
                "message": "'os' imported but unused",
                "location": {"row": 1, "column": 1},
            }
        ]
        with patch(
            "subprocess.run",
            return_value=self._mock_run(diagnostics, returncode=1),
        ):
            result = self.ruff.generate([pyi], self.tmp)
        self.assertEqual(result, {})

    def test_invalid_json_returns_empty(self):
        pyi = self.tmp / "any.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        mock = MagicMock()
        mock.stdout = "not json"
        mock.returncode = 1
        with patch("subprocess.run", return_value=mock):
            result = self.ruff.generate([pyi], self.tmp)
        self.assertEqual(result, {})

    def test_default_select(self):
        self.assertEqual(self.ruff.select, ("FA", "I", "ICN001", "RUF100"))

    def test_type_is_ruff(self):
        self.assertEqual(self.ruff.type, "ruff")

    def test_select_passed_to_command(self):
        pyi = self.tmp / "check.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = MagicMock()
            m.stdout = _make_ruff_output([])
            m.returncode = 0
            return m

        ruff = Ruff(select=("E", "W"))
        with patch("subprocess.run", side_effect=fake_run):
            ruff.generate([pyi], self.tmp)

        self.assertTrue(any("--select=E,W" in arg for arg in captured["cmd"]))

    def test_unsafe_fixes_flag(self):
        pyi = self.tmp / "check.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = MagicMock()
            m.stdout = _make_ruff_output([])
            m.returncode = 0
            return m

        ruff = Ruff(unsafe_fixes=True)
        with patch("subprocess.run", side_effect=fake_run):
            ruff.generate([pyi], self.tmp)

        self.assertIn("--unsafe-fixes", captured["cmd"])


class TestRuffIntegration(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_detects_unsorted_imports(self):
        pyi = self.tmp / "imports.pyi"
        pyi.write_text("import sys\nimport os\n\ndef foo() -> None: ...\n")
        ruff = Ruff(select=("I",))
        result = ruff.generate([pyi], self.tmp)
        self.assertIn(pyi, result)

    def test_clean_file_no_errors(self):
        pyi = self.tmp / "clean.pyi"
        pyi.write_text("def foo(x: int) -> str: ...\n")
        ruff = Ruff(select=("I",))
        result = ruff.generate([pyi], self.tmp)
        self.assertEqual(result, {})
