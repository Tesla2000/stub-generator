import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.process._ruff_fix import RuffFix


class TestRuffFix(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fixer = RuffFix()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- isort (extend_select=I default) ---

    def test_sorts_imports(self):
        pyi = self.tmp / "unsorted.pyi"
        pyi.write_text(
            "import sys\nimport os\n\ndef foo(x: os.PathLike) -> sys.version_info: ...\n"
        )
        self.fixer.process([pyi])
        content = pyi.read_text()
        self.assertLess(
            content.index("import os"), content.index("import sys")
        )

    def test_already_sorted_unchanged(self):
        src = "import os\nimport sys\n\ndef foo(x: os.PathLike) -> sys.version_info: ...\n"
        pyi = self.tmp / "sorted.pyi"
        pyi.write_text(src)
        self.fixer.process([pyi])
        self.assertEqual(pyi.read_text(), src)

    def test_sorts_multiple_files(self):
        pyi1 = self.tmp / "a.pyi"
        pyi2 = self.tmp / "b.pyi"
        pyi1.write_text(
            "import sys\nimport os\n\nx: os.PathLike\ny: sys.version_info\n"
        )
        pyi2.write_text(
            "import typing\nimport abc\n\nz: abc.ABC\nw: typing.Any\n"
        )
        self.fixer.process([pyi1, pyi2])
        c1, c2 = pyi1.read_text(), pyi2.read_text()
        self.assertLess(c1.index("import os"), c1.index("import sys"))
        self.assertLess(c2.index("import abc"), c2.index("import typing"))

    # --- select / extend_select ---

    def test_select_overrides_default(self):
        fixer = RuffFix(select=("I",), extend_select=())
        pyi = self.tmp / "sel.pyi"
        pyi.write_text(
            "import sys\nimport os\n\ndef foo(x: os.PathLike) -> sys.version_info: ...\n"
        )
        fixer.process([pyi])
        content = pyi.read_text()
        self.assertLess(
            content.index("import os"), content.index("import sys")
        )

    def test_extend_select_empty_disables_isort(self):
        fixer = RuffFix(extend_select=())
        pyi = self.tmp / "no_isort.pyi"
        src = "import sys\nimport os\n\nx: os.PathLike\ny: sys.version_info\n"
        pyi.write_text(src)
        fixer.process([pyi])
        content = pyi.read_text()
        # Without I rule, import order is untouched
        self.assertLess(
            content.index("import sys"), content.index("import os")
        )

    # --- misc ---

    def test_clean_file_unchanged(self):
        src = "import os\n\ndef foo(x: os.PathLike) -> None: ...\n"
        pyi = self.tmp / "clean.pyi"
        pyi.write_text(src)
        self.fixer.process([pyi])
        self.assertEqual(pyi.read_text(), src)

    def test_type_is_ruff_fix(self):
        self.assertEqual(self.fixer.type, "ruff_fix")

    def test_default_extend_select_includes_i(self):
        self.assertIn("I", RuffFix().extend_select)
