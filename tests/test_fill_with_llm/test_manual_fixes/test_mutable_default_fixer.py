import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.mutable_default_fixer import (
    MutableDefaultFixer,
)


class TestMutableDefaultFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = MutableDefaultFixer()

    def test_applicable_with_b008_error(self):
        errors = [
            "file.pyi:29:58: B008 Do not perform function call `Foo` in argument defaults"
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_b008(self):
        errors = ["file.pyi:1:1: F401 'os' imported but unused"]
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestMutableDefaultFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = MutableDefaultFixer()

    def test_no_b008_errors_unchanged(self):
        src = "def foo(x: int = 0) -> None: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_replaces_call_default_with_ellipsis(self):
        src = textwrap.dedent("""\
            class Cfg: ...

            def foo(cfg: Cfg = Cfg()) -> None: ...
        """)
        errors = [
            "file.pyi:3:20: B008 Do not perform function call `Cfg` in argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("cfg: Cfg = ...", result)
        self.assertNotIn("Cfg()", result)

    def test_replaces_call_with_args(self):
        src = "def foo(x: int = int(42)) -> None: ...\n"
        errors = [
            "file.pyi:1:17: B008 Do not perform function call `int` in argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: int = ...", result)
        self.assertNotIn("int(42)", result)

    def test_multiple_calls_same_line(self):
        src = "def foo(a: A = A(), b: B = B()) -> None: ...\n"
        errors = [
            "file.pyi:1:15: B008 Do not perform function call `A` in argument defaults",
            "file.pyi:1:27: B008 Do not perform function call `B` in argument defaults",
        ]
        result = self.fixer(src, errors)
        self.assertIn("a: A = ...", result)
        self.assertIn("b: B = ...", result)

    def test_multiple_functions(self):
        src = textwrap.dedent("""\
            def foo(x: Cfg = Cfg()) -> None: ...
            def bar(y: Cfg = Cfg()) -> None: ...
        """)
        errors = [
            "file.pyi:1:17: B008 Do not perform function call `Cfg` in argument defaults",
            "file.pyi:2:17: B008 Do not perform function call `Cfg` in argument defaults",
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: Cfg = ...", result)
        self.assertIn("y: Cfg = ...", result)
        self.assertNotIn("Cfg()", result)

    def test_kwonly_default_replaced(self):
        src = "def foo(*, x: Cfg = Cfg()) -> None: ...\n"
        errors = [
            "file.pyi:1:20: B008 Do not perform function call `Cfg` in argument defaults"
        ]
        result = self.fixer(src, errors)
        self.assertIn("x: Cfg = ...", result)

    def test_type_is_call_default(self):
        self.assertEqual(self.fixer.type, "mutable_default")
