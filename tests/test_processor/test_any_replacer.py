import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._any_replacer import AnyReplacer


class TestAnyReplacer(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.replacer = AnyReplacer()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_replaces_any_in_parameter_annotation(self):
        pyi = self.tmp / "param.pyi"
        pyi.write_text("def foo(x: Any) -> None: ...\n")
        self.replacer.process([pyi])
        self.assertIn("x: object", pyi.read_text())

    def test_replaces_any_in_return_annotation(self):
        pyi = self.tmp / "ret.pyi"
        pyi.write_text("def foo() -> Any: ...\n")
        self.replacer.process([pyi])
        self.assertIn("-> object", pyi.read_text())

    def test_replaces_any_in_variable_annotation(self):
        pyi = self.tmp / "var.pyi"
        pyi.write_text("x: Any\n")
        self.replacer.process([pyi])
        self.assertIn("x: object", pyi.read_text())

    def test_replaces_any_in_subscript(self):
        pyi = self.tmp / "sub.pyi"
        pyi.write_text("def foo(x: list[Any]) -> dict[str, Any]: ...\n")
        self.replacer.process([pyi])
        result = pyi.read_text()
        self.assertIn("list[object]", result)
        self.assertIn("dict[str, object]", result)

    def test_no_any_unchanged(self):
        src = "def foo(x: int) -> None: ...\n"
        pyi = self.tmp / "clean.pyi"
        pyi.write_text(src)
        mtime_before = pyi.stat().st_mtime
        self.replacer.process([pyi])
        self.assertEqual(pyi.stat().st_mtime, mtime_before)

    def test_does_not_replace_anystr(self):
        src = "from typing import AnyStr\ndef foo(x: AnyStr) -> AnyStr: ...\n"
        pyi = self.tmp / "anystr.pyi"
        pyi.write_text(src)
        self.replacer.process([pyi])
        self.assertIn("AnyStr", pyi.read_text())

    def test_multiple_files(self):
        pyi1 = self.tmp / "a.pyi"
        pyi2 = self.tmp / "b.pyi"
        pyi1.write_text("def a(x: Any) -> None: ...\n")
        pyi2.write_text("def b() -> Any: ...\n")
        self.replacer.process([pyi1, pyi2])
        self.assertIn("x: object", pyi1.read_text())
        self.assertIn("-> object", pyi2.read_text())

    def test_type_is_any_replacer(self):
        self.assertEqual(self.replacer.type, "any_replacer")
