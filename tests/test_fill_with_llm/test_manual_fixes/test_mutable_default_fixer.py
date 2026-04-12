import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.mutable_default_fixer import (
    MutableDefaultFixer,
)


class TestMutableDefaultFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = MutableDefaultFixer()

    def test_applicable_with_b008(self):
        self.assertTrue(
            self.fixer.is_applicable(
                [
                    "file.pyi:1:17: B008 Do not use mutable data structures for argument defaults"
                ]
            )
        )

    def test_applicable_with_y011(self):
        self.assertTrue(
            self.fixer.is_applicable(
                [
                    "file.pyi:1:17: Y011 Default values for typed function arguments must be simple"
                ]
            )
        )

    def test_not_applicable_without_b008_y011(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: F401 'os' imported but unused"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestMutableDefaultFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = MutableDefaultFixer()

    def test_no_errors_unchanged(self):
        src = "def foo(x: list[int] = []) -> None: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_replaces_list_default(self):
        # [] is at col 24 (1-based)
        src = "def foo(x: list[int] = []) -> None: ...\n"
        errors = [
            "file.pyi:1:24: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: list[int] = ...", result)
        self.assertNotIn("[]", result)

    def test_replaces_dict_default(self):
        # {} is at col 29 (1-based)
        src = "def foo(x: dict[str, int] = {}) -> None: ...\n"
        errors = [
            "file.pyi:1:29: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: dict[str, int] = ...", result)
        self.assertNotIn("{}", result)

    def test_replaces_set_call_default(self):
        # set() is at col 23 (1-based)
        src = "def foo(x: set[int] = set()) -> None: ...\n"
        errors = [
            "file.pyi:1:23: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: set[int] = ...", result)
        self.assertNotIn("set()", result)

    def test_only_errored_default_replaced(self):
        # Two list defaults; only the second (col 43) has an error — first must survive.
        src = "def foo(a: list[int] = [], b: list[str] = []) -> None: ...\n"
        errors = [
            "file.pyi:1:43: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("a: list[int] = []", result)
        self.assertIn("b: list[str] = ...", result)

    def test_multiple_errors_same_line(self):
        # [] at col 24, {} at col 29 after adjusting for longer first arg...
        # Use a simpler two-arg case with known offsets.
        src = (
            "def foo(a: list[int] = [], b: dict[str, int] = {}) -> None: ...\n"
        )
        # a's [] at col 24, b's {} at col 48
        errors = [
            "file.pyi:1:24: B008 Do not use mutable data structures for argument defaults",
            "file.pyi:1:48: B008 Do not use mutable data structures for argument defaults",
        ]
        result = self.fixer(src, errors)
        self.assertIn("a: list[int] = ...", result)
        self.assertIn("b: dict[str, int] = ...", result)

    def test_multiple_functions(self):
        src = textwrap.dedent("""\
            def foo(x: list[int] = []) -> None: ...
            def bar(y: dict[str, int] = {}) -> None: ...
        """)
        errors = [
            "file.pyi:1:24: B008 Do not use mutable data structures for argument defaults",
            "file.pyi:2:29: B008 Do not use mutable data structures for argument defaults",
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: list[int] = ...", result)
        self.assertIn("y: dict[str, int] = ...", result)

    def test_kwonly_default_replaced(self):
        # [] is at col 27 (1-based) for kwonly arg
        src = "def foo(*, x: list[int] = []) -> None: ...\n"
        errors = [
            "file.pyi:1:27: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: list[int] = ...", result)

    def test_regular_class_annotated_field(self):
        # Regular class, annotated: x: list[int] = [] — [] at col 20 (1-based)
        src = "class Foo:\n    x: list[int] = []\n"
        errors = [
            "file.pyi:2:20: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: list[int] = ...", result)
        self.assertNotIn("[]", result)

    def test_regular_class_untyped_field(self):
        # Regular class, untyped: x = [] — [] at col 9 (1-based)
        src = "class Foo:\n    x = []\n"
        errors = [
            "file.pyi:2:9: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x = ...", result)
        self.assertNotIn("[]", result)

    def test_namedtuple_field_list_default(self):
        # x: list[int] = [] — [] at col 20 (1-based)
        src = "class Foo(NamedTuple):\n    x: list[int] = []\n"
        errors = [
            "file.pyi:2:20: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: list[int] = ...", result)
        self.assertNotIn("[]", result)

    def test_namedtuple_field_dict_default(self):
        # y: dict[str, int] = {} — {} at col 25 (1-based)
        src = "class Foo(NamedTuple):\n    x: list[int] = []\n    y: dict[str, int] = {}\n"
        errors = [
            "file.pyi:3:25: B008 Do not use mutable data structures for argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: list[int] = []", result)  # untouched
        self.assertIn("y: dict[str, int] = ...", result)

    def test_type_is_mutable_default(self):
        self.assertEqual(self.fixer.type, "mutable_default")
