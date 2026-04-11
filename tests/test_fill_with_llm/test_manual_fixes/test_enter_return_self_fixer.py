import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.enter_return_self_fixer import (
    EnterReturnSelfFixer,
)


class TestEnterReturnSelfFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = EnterReturnSelfFixer()

    def test_applicable_with_y034(self):
        errors = [
            'file.pyi:26:5: Y034 "__enter__" methods in classes like "TimeoutGuard" usually return "self" at runtime.'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_y034(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: F401 'os' imported but unused"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestEnterReturnSelfFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = EnterReturnSelfFixer()

    def _y034(self, cls: str) -> list[str]:
        return [
            f'file.pyi:2:5: Y034 "__enter__" methods in classes like "{cls}" usually return "self" at runtime.'
        ]

    def test_no_y034_unchanged(self):
        src = "class Foo:\n    def __enter__(self) -> Self: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_replaces_classname_return_with_self(self):
        src = textwrap.dedent("""\
            class TimeoutGuard:
                def __enter__(self) -> TimeoutGuard: ...
        """)
        result = self.fixer(src, self._y034("TimeoutGuard"))
        self.assertIn("-> Self", result)
        self.assertNotIn("-> TimeoutGuard", result)

    def test_adds_self_import(self):
        src = textwrap.dedent("""\
            class Foo:
                def __enter__(self) -> Foo: ...
        """)
        result = self.fixer(src, self._y034("Foo"))
        self.assertIn("from typing_extensions import Self", result)

    def test_does_not_duplicate_self_import(self):
        src = textwrap.dedent("""\
            from typing_extensions import Self

            class Foo:
                def __enter__(self) -> Foo: ...
        """)
        result = self.fixer(src, self._y034("Foo"))
        self.assertEqual(result.count("from typing_extensions import Self"), 1)

    def test_only_affects_named_class(self):
        src = textwrap.dedent("""\
            class A:
                def __enter__(self) -> A: ...

            class B:
                def __enter__(self) -> B: ...
        """)
        result = self.fixer(src, self._y034("A"))
        self.assertIn("class A:\n    def __enter__(self) -> Self", result)
        self.assertIn("-> B:", result)

    def test_type_is_enter_return_self(self):
        self.assertEqual(self.fixer.type, "enter_return_self")
