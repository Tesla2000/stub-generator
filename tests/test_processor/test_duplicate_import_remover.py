import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._duplicate_import_remover import (
    DuplicateImportRemover,
)


class TestDuplicateImportRemover(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.remover = DuplicateImportRemover()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_removes_duplicate_aliased_names(self):
        pyi = self.tmp / "dup.pyi"
        pyi.write_text(
            "from google.auth.transport import Request as _Request, Request as _Request\n"
        )
        self.remover.process([pyi])
        result = pyi.read_text()
        self.assertEqual(result.count("Request as _Request"), 1)

    def test_removes_multiple_duplicates_same_line(self):
        pyi = self.tmp / "multi.pyi"
        pyi.write_text("from pkg import A, B, A, C, B\n")
        self.remover.process([pyi])
        result = pyi.read_text()
        self.assertEqual(result.count(" A"), 1)
        self.assertEqual(result.count(" B"), 1)
        self.assertIn("C", result)

    def test_no_duplicates_unchanged(self):
        src = "from pkg import A, B, C\n"
        pyi = self.tmp / "clean.pyi"
        pyi.write_text(src)
        mtime_before = pyi.stat().st_mtime
        self.remover.process([pyi])
        self.assertEqual(pyi.stat().st_mtime, mtime_before)

    def test_same_name_different_alias_kept(self):
        pyi = self.tmp / "alias.pyi"
        pyi.write_text(
            "from pkg import Request as _Request, Request as _Req\n"
        )
        self.remover.process([pyi])
        result = pyi.read_text()
        self.assertIn("_Request", result)
        self.assertIn("_Req", result)

    def test_multiple_files(self):
        pyi1 = self.tmp / "a.pyi"
        pyi2 = self.tmp / "b.pyi"
        pyi1.write_text("from pkg import X, X\n")
        pyi2.write_text("from pkg import Y, Y, Y\n")
        self.remover.process([pyi1, pyi2])
        self.assertEqual(pyi1.read_text().count(" X"), 1)
        self.assertEqual(pyi2.read_text().count(" Y"), 1)

    def test_type_is_duplicate_import_remover(self):
        self.assertEqual(self.remover.type, "duplicate_import_remover")
