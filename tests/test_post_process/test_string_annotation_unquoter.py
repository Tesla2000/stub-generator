import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._string_annotation_unquoter import (
    StringAnnotationUnquoter,
)


class TestStringAnnotationUnquoter(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.unquoter = StringAnnotationUnquoter()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unquotes_variable_annotation(self):
        pyi = self.tmp / "ann.pyi"
        pyi.write_text('x: "int"\n')
        self.unquoter.process([pyi])
        self.assertIn("x: int", pyi.read_text())

    def test_unquotes_union_annotation(self):
        pyi = self.tmp / "union.pyi"
        pyi.write_text('class DataInt(int): ...\nx: "DataInt | None"\n')
        self.unquoter.process([pyi])
        self.assertIn("x: DataInt | None", pyi.read_text())

    def test_unquotes_return_type(self):
        pyi = self.tmp / "ret.pyi"
        pyi.write_text('def foo() -> "int": ...\n')
        self.unquoter.process([pyi])
        self.assertIn("-> int", pyi.read_text())

    def test_unquotes_parameter_annotation(self):
        pyi = self.tmp / "param.pyi"
        pyi.write_text('def foo(x: "str") -> None: ...\n')
        self.unquoter.process([pyi])
        self.assertIn("x: str", pyi.read_text())

    def test_clean_file_not_rewritten(self):
        src = "def foo(x: int) -> None: ...\n"
        pyi = self.tmp / "clean.pyi"
        pyi.write_text(src)
        mtime_before = pyi.stat().st_mtime
        self.unquoter.process([pyi])
        self.assertEqual(pyi.stat().st_mtime, mtime_before)

    def test_type_is_string_annotation_unquoter(self):
        self.assertEqual(self.unquoter.type, "string_annotation_unquoter")
