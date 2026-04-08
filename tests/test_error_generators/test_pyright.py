import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from stub_added.transformer.error_generator import Pyright


def _make_pyright_output(diagnostics: list[dict]) -> str:
    return json.dumps({"generalDiagnostics": diagnostics})


class TestPyrightGenerate(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _mock_run(self, diagnostics: list[dict], returncode: int = 1):
        mock = MagicMock()
        mock.stdout = _make_pyright_output(diagnostics)
        mock.returncode = returncode
        return mock

    def test_no_errors_returns_empty(self):
        pyi = self.tmp_path / "clean.pyi"
        pyi.write_text("def foo(x: int) -> str: ...\n")

        with patch(
            "subprocess.run", return_value=self._mock_run([], returncode=0)
        ):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertEqual(result, {})

    def test_error_for_known_file_returned(self):
        pyi = self.tmp_path / "bad.pyi"
        pyi.write_text("x: int = 'hello'\n")

        diagnostics = [
            {
                "file": str(pyi),
                "severity": "error",
                "message": (
                    'Expression of type "str" cannot be assigned to declared type "int"'
                ),
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 10},
                },
            }
        ]
        with patch("subprocess.run", return_value=self._mock_run(diagnostics)):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertIn(pyi, result)
        self.assertEqual(len(result[pyi]), 1)
        self.assertIn("error:", result[pyi][0])
        self.assertIn(str(pyi), result[pyi][0])

    def test_warnings_not_included(self):
        pyi = self.tmp_path / "warn.pyi"
        pyi.write_text("def foo() -> None: ...\n")

        diagnostics = [
            {
                "file": str(pyi),
                "severity": "warning",
                "message": "Some warning",
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 3},
                },
            }
        ]
        with patch("subprocess.run", return_value=self._mock_run(diagnostics)):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertEqual(result, {})

    def test_error_for_unknown_file_excluded(self):
        pyi = self.tmp_path / "known.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        other = self.tmp_path / "other.pyi"

        diagnostics = [
            {
                "file": str(other),
                "severity": "error",
                "message": "Some error",
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 3},
                },
            }
        ]
        with patch("subprocess.run", return_value=self._mock_run(diagnostics)):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertNotIn(other, result)
        self.assertEqual(result, {})

    def test_multiple_errors_same_file(self):
        pyi = self.tmp_path / "multi.pyi"
        pyi.write_text("x: int = 'a'\ny: str = 1\n")

        diagnostics = [
            {
                "file": str(pyi),
                "severity": "error",
                "message": "Error on line 1",
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 1},
                },
            },
            {
                "file": str(pyi),
                "severity": "error",
                "message": "Error on line 2",
                "range": {
                    "start": {"line": 1, "character": 0},
                    "end": {"line": 1, "character": 1},
                },
            },
        ]
        with patch("subprocess.run", return_value=self._mock_run(diagnostics)):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertIn(pyi, result)
        self.assertEqual(len(result[pyi]), 2)

    def test_line_numbers_are_1_based(self):
        pyi = self.tmp_path / "lineno.pyi"
        pyi.write_text("x: int = 'hello'\n")

        diagnostics = [
            {
                "file": str(pyi),
                "severity": "error",
                "message": "Type error",
                "range": {
                    "start": {"line": 2, "character": 0},
                    "end": {"line": 2, "character": 5},
                },
            }
        ]
        with patch("subprocess.run", return_value=self._mock_run(diagnostics)):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertIn(":3:", result[pyi][0])

    def test_invalid_json_returns_empty(self):
        pyi = self.tmp_path / "any.pyi"
        pyi.write_text("def foo() -> None: ...\n")

        mock = MagicMock()
        mock.stdout = "not json output"
        mock.returncode = 1

        with patch("subprocess.run", return_value=mock):
            result = Pyright.generate([pyi], self.tmp_path)

        self.assertEqual(result, {})

    def test_stubs_dir_added_to_pythonpath(self):
        pyi = self.tmp_path / "check.pyi"
        pyi.write_text("def foo() -> None: ...\n")
        stubs_dir = self.tmp_path / "stubs"

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env", {})
            m = MagicMock()
            m.stdout = _make_pyright_output([])
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            Pyright.generate([pyi], stubs_dir)

        self.assertIn(str(stubs_dir), captured["env"].get("PYTHONPATH", ""))
