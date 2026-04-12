import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._pre_commit_hooks import PreCommitHooks


class TestPreCommitHooks(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.hooks = PreCommitHooks()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, content: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(content)
        return path

    def test_strips_trailing_whitespace(self):
        pyi = self._write("a.pyi", b"def foo() -> None: ...   \nx: int  \n")
        self.hooks.process([pyi])
        self.assertEqual(pyi.read_text(), "def foo() -> None: ...\nx: int\n")

    def test_ensures_trailing_newline(self):
        pyi = self._write("a.pyi", b"def foo() -> None: ...")
        self.hooks.process([pyi])
        self.assertTrue(pyi.read_text().endswith("\n"))

    def test_removes_multiple_trailing_newlines(self):
        pyi = self._write("a.pyi", b"def foo() -> None: ...\n\n\n")
        self.hooks.process([pyi])
        self.assertEqual(pyi.read_text(), "def foo() -> None: ...\n")

    def test_normalizes_crlf_to_lf(self):
        pyi = self._write("a.pyi", b"def foo() -> None: ...\r\nx: int\r\n")
        self.hooks.process([pyi])
        self.assertNotIn("\r", pyi.read_text())
        self.assertIn("\n", pyi.read_text())

    def test_normalizes_cr_to_lf(self):
        pyi = self._write("a.pyi", b"def foo() -> None: ...\rx: int\r")
        self.hooks.process([pyi])
        self.assertNotIn("\r", pyi.read_text())

    def test_already_clean_file_unchanged(self):
        content = "def foo() -> None: ...\nx: int\n"
        pyi = self._write("a.pyi", content.encode())
        self.hooks.process([pyi])
        self.assertEqual(pyi.read_text(), content)

    def test_multiple_files(self):
        pyi1 = self._write("a.pyi", b"x: int   \n")
        pyi2 = self._write("b.pyi", b"y: str  \n\n")
        self.hooks.process([pyi1, pyi2])
        self.assertEqual(pyi1.read_text(), "x: int\n")
        self.assertEqual(pyi2.read_text(), "y: str\n")

    def test_type_is_pre_commit_hooks(self):
        self.assertEqual(self.hooks.type, "pre_commit_hooks")
