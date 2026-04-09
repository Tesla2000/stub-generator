import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from stub_adder.transformer.error_generator import Pyright
from stub_adder.transformer.error_generator._pyright import PyrightConfig


def _make_pyright_output(diagnostics: list[dict]) -> str:
    return json.dumps({"generalDiagnostics": diagnostics})


class TestPyrightConfig(TestCase):
    def test_serializes_to_camel_case(self):
        cfg = PyrightConfig().model_dump(by_alias=True)
        self.assertIn("typeCheckingMode", cfg)
        self.assertIn("reportIncompleteStub", cfg)
        self.assertIn("enableTypeIgnoreComments", cfg)
        self.assertNotIn("type_checking_mode", cfg)
        self.assertNotIn("report_incomplete_stub", cfg)

    def test_default_values_match_typeshed(self):
        cfg = PyrightConfig()
        self.assertEqual(cfg.type_checking_mode, "strict")
        self.assertEqual(cfg.report_incomplete_stub, "none")
        self.assertEqual(cfg.report_call_in_default_initializer, "error")
        self.assertEqual(cfg.report_unnecessary_type_ignore_comment, "error")
        self.assertFalse(cfg.enable_type_ignore_comments)

    def test_typeshed_path_in_config_included(self):
        pyright = Pyright(
            config=PyrightConfig(typeshed_path="/custom/typeshed")
        )
        cfg = pyright._build_config()
        self.assertEqual(cfg["typeshedPath"], "/custom/typeshed")

    def test_typeshed_path_absent_not_in_config(self):
        cfg = Pyright()._build_config()
        self.assertNotIn("typeshedPath", cfg)

    def test_build_config_keys_are_camel_case(self):
        cfg = Pyright()._build_config()
        self.assertIn("typeCheckingMode", cfg)
        self.assertNotIn("type_checking_mode", cfg)

    def test_custom_config_reflected_in_build(self):
        pyright = Pyright(config=PyrightConfig(type_checking_mode="basic"))
        cfg = pyright._build_config()
        self.assertEqual(cfg["typeCheckingMode"], "basic")

    def test_populate_by_name(self):
        cfg = PyrightConfig(type_checking_mode="off")
        self.assertEqual(cfg.type_checking_mode, "off")


class TestPyrightGenerate(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.pyright = Pyright()

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
            result = self.pyright.generate([pyi], self.tmp_path)

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
            result = self.pyright.generate([pyi], self.tmp_path)

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
            result = self.pyright.generate([pyi], self.tmp_path)

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
            result = self.pyright.generate([pyi], self.tmp_path)

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
            result = self.pyright.generate([pyi], self.tmp_path)

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
            result = self.pyright.generate([pyi], self.tmp_path)

        self.assertIn(":3:", result[pyi][0])

    def test_invalid_json_returns_empty(self):
        pyi = self.tmp_path / "any.pyi"
        pyi.write_text("def foo() -> None: ...\n")

        mock = MagicMock()
        mock.stdout = "not json output"
        mock.returncode = 1

        with patch("subprocess.run", return_value=mock):
            result = self.pyright.generate([pyi], self.tmp_path)

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
            self.pyright.generate([pyi], stubs_dir)

        self.assertIn(str(stubs_dir), captured["env"].get("PYTHONPATH", ""))

    def test_relative_paths_resolved_to_absolute(self):
        pyi_abs = self.tmp_path / "rel.pyi"
        pyi_abs.write_text("def foo() -> None: ...\n")
        pyi_rel = (
            pyi_abs.relative_to(Path.cwd())
            if pyi_abs.is_relative_to(Path.cwd())
            else pyi_abs
        )

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env", {})
            m = MagicMock()
            m.stdout = _make_pyright_output(
                [
                    {
                        "file": str(pyi_abs),
                        "severity": "error",
                        "message": "Some error",
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 1},
                        },
                    }
                ]
            )
            m.returncode = 1
            return m

        with patch("subprocess.run", side_effect=fake_run):
            result = self.pyright.generate([pyi_rel], self.tmp_path)

        # All paths passed to subprocess must be absolute
        for arg in captured["cmd"]:
            if arg.endswith(".pyi"):
                self.assertTrue(
                    Path(arg).is_absolute(),
                    f"Expected absolute path, got: {arg}",
                )
        # Error must be returned even when input path was relative
        self.assertIn(pyi_abs, result)

    def test_project_config_passed_to_pyright(self):
        pyi = self.tmp_path / "check.pyi"
        pyi.write_text("def foo() -> None: ...\n")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = MagicMock()
            m.stdout = _make_pyright_output([])
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            self.pyright.generate([pyi], self.tmp_path)

        self.assertIn("--project", captured["cmd"])
