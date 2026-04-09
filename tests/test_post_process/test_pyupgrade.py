import tempfile
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.post_process._pyupgrade import Pyupgrade


class TestPyupgrade(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pyupgrade = Pyupgrade()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_upgrades_union_syntax(self):
        pyi = self.tmp / "union.pyi"
        pyi.write_text(
            "from typing import Optional\n\ndef foo(x: Optional[int]) -> None: ...\n"
        )
        Pyupgrade(min_version=(3, 10)).process([pyi])
        result = pyi.read_text()
        self.assertIn("int | None", result)

    def test_already_modern_unchanged(self):
        src = "def foo(x: int | None) -> None: ...\n"
        pyi = self.tmp / "modern.pyi"
        pyi.write_text(src)
        Pyupgrade(min_version=(3, 10)).process([pyi])
        self.assertEqual(pyi.read_text(), src)

    def test_multiple_files(self):
        pyi1 = self.tmp / "a.pyi"
        pyi2 = self.tmp / "b.pyi"
        pyi1.write_text(
            "from typing import Optional\n\ndef a(x: Optional[str]) -> None: ...\n"
        )
        pyi2.write_text(
            "from typing import Optional\n\ndef b(x: Optional[int]) -> None: ...\n"
        )
        Pyupgrade(min_version=(3, 10)).process([pyi1, pyi2])
        self.assertIn("str | None", pyi1.read_text())
        self.assertIn("int | None", pyi2.read_text())

    def test_default_min_version(self):
        self.assertEqual(self.pyupgrade.min_version, (3, 9))

    def test_type_is_pyupgrade(self):
        self.assertEqual(self.pyupgrade.type, "pyupgrade")
