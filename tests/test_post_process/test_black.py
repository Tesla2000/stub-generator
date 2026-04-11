import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._black import Black


class TestBlack(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.black = Black()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_formats_file_in_place(self):
        pyi = self.tmp / "ugly.pyi"
        pyi.write_text("def foo(x:int)->str: ...\n")
        self.black.process([pyi])
        self.assertIn("def foo(x: int) -> str:", pyi.read_text())

    def test_already_formatted_unchanged(self):
        src = "def foo(x: int) -> str: ...\n"
        pyi = self.tmp / "clean.pyi"
        pyi.write_text(src)
        self.black.process([pyi])
        self.assertEqual(pyi.read_text(), src)

    def test_multiple_files(self):
        pyi1 = self.tmp / "a.pyi"
        pyi2 = self.tmp / "b.pyi"
        pyi1.write_text("def a(x:int)->None: ...\n")
        pyi2.write_text("def b(y:str)->int: ...\n")
        self.black.process([pyi1, pyi2])
        self.assertIn("def a(x: int) -> None:", pyi1.read_text())
        self.assertIn("def b(y: str) -> int:", pyi2.read_text())

    def test_type_is_black(self):
        self.assertEqual(self.black.type, "black")
