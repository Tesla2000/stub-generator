import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._ruff_isort import RuffIsort


class TestRuffIsort(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.ruff_isort = RuffIsort()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sorts_imports(self):
        pyi = self.tmp / "unsorted.pyi"
        pyi.write_text("import sys\nimport os\n\ndef foo() -> None: ...\n")
        self.ruff_isort.process([pyi])
        content = pyi.read_text()
        self.assertLess(
            content.index("import os"), content.index("import sys")
        )

    def test_already_sorted_unchanged(self):
        src = "import os\nimport sys\n\ndef foo() -> None: ...\n"
        pyi = self.tmp / "sorted.pyi"
        pyi.write_text(src)
        self.ruff_isort.process([pyi])
        self.assertEqual(pyi.read_text(), src)

    def test_multiple_files(self):
        pyi1 = self.tmp / "a.pyi"
        pyi2 = self.tmp / "b.pyi"
        pyi1.write_text("import sys\nimport os\n\nx: int\n")
        pyi2.write_text("import typing\nimport abc\n\ny: str\n")
        self.ruff_isort.process([pyi1, pyi2])
        c1, c2 = pyi1.read_text(), pyi2.read_text()
        self.assertLess(c1.index("import os"), c1.index("import sys"))
        self.assertLess(c2.index("import abc"), c2.index("import typing"))

    def test_type_is_ruff_isort(self):
        self.assertEqual(self.ruff_isort.type, "ruff_isort")
