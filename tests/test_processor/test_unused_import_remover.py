import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._unused_import_remover import (
    UnusedImportRemover,
)


class TestUnusedImportRemover(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.remover = UnusedImportRemover()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_removes_unused_import(self):
        pyi = self.tmp / "unused.pyi"
        pyi.write_text("import os\n\ndef foo() -> None: ...\n")
        self.remover.process([pyi])
        self.assertNotIn("import os", pyi.read_text())

    def test_keeps_used_import(self):
        pyi = self.tmp / "used.pyi"
        pyi.write_text("import os\n\ndef foo() -> os.PathLike: ...\n")
        self.remover.process([pyi])
        self.assertIn("import os", pyi.read_text())

    def test_clean_file_unchanged(self):
        src = "def foo(x: int) -> None: ...\n"
        pyi = self.tmp / "clean.pyi"
        pyi.write_text(src)
        self.remover.process([pyi])
        self.assertEqual(pyi.read_text(), src)

    def test_type_is_unused_import_remover(self):
        self.assertEqual(self.remover.type, "unused_import_remover")
