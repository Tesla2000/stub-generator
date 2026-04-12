import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.type_checking_fixer import (
    TypeCheckingFixer,
)


class TestTypeCheckingFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = TypeCheckingFixer()

    def test_applicable_with_y002(self):
        self.assertTrue(
            self.fixer.is_applicable(
                ["file.pyi:7:4: Y002 If test must be a simple comparison"]
            )
        )

    def test_not_applicable_without_y002(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: Y021 Docstrings not allowed"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestTypeCheckingFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = TypeCheckingFixer()
        self.errors = [
            "file.pyi:7:4: Y002 If test must be a simple comparison"
        ]

    def test_no_y002_unchanged(self):
        src = "def foo() -> None: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_unwraps_type_checking_block(self):
        src = textwrap.dedent("""\
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from os import PathLike
            def foo() -> None: ...
        """)
        result = self.fixer(src, self.errors)
        self.assertIn("from os import PathLike", result)
        self.assertNotIn("if TYPE_CHECKING", result)

    def test_removes_type_checking_import_when_unused(self):
        src = textwrap.dedent("""\
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from os import PathLike
            def foo() -> None: ...
        """)
        result = self.fixer(src, self.errors)
        self.assertNotIn("TYPE_CHECKING", result)

    def test_keeps_type_checking_import_when_still_used(self):
        src = textwrap.dedent("""\
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from os import PathLike
            x: TYPE_CHECKING
        """)
        result = self.fixer(src, self.errors)
        self.assertIn("TYPE_CHECKING", result)

    def test_keeps_other_names_in_import(self):
        src = textwrap.dedent("""\
            from typing import TYPE_CHECKING, Any
            if TYPE_CHECKING:
                from os import PathLike
            def foo(x: Any) -> None: ...
        """)
        result = self.fixer(src, self.errors)
        self.assertNotIn("TYPE_CHECKING", result)
        self.assertIn("from typing import Any", result)

    def test_multiple_imports_in_block(self):
        src = textwrap.dedent("""\
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from os import PathLike
                from collections.abc import Sequence
            def foo() -> None: ...
        """)
        result = self.fixer(src, self.errors)
        self.assertIn("from os import PathLike", result)
        self.assertIn("from collections.abc import Sequence", result)
        self.assertNotIn("if TYPE_CHECKING", result)

    def test_type_is_type_checking(self):
        self.assertEqual(self.fixer.type, "type_checking")
