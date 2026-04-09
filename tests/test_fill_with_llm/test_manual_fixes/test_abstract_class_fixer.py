import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.abstract_class_fixer import (
    AbstractClassFixer,
)


class TestAbstractClassFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = AbstractClassFixer()

    def test_applicable_with_abstract_error(self):
        errors = [
            'f.pyi:1: error: Class pkg.Foo has abstract attributes "bar"  [misc]'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_abstract_error(self):
        errors = ['f.pyi:1: error: Name "Foo" is not defined  [name-defined]']
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestAbstractClassFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = AbstractClassFixer()

    def test_adds_abc_metaclass(self):
        src = textwrap.dedent("""\
            class Foo:
                def bar(self) -> None: ...
        """)
        errors = [
            'f.pyi:1: error: Class pkg.Foo has abstract attributes "bar"  [misc]'
        ]
        result = self.fixer(src, errors)
        self.assertIn("metaclass=abc.ABCMeta", result)
        self.assertIn("import abc", result)

    def test_no_change_without_error(self):
        src = "class Foo: ...\n"
        result = self.fixer(src, [])
        self.assertEqual(result, src)

    def test_does_not_duplicate_metaclass(self):
        src = textwrap.dedent("""\
            import abc
            class Foo(metaclass=abc.ABCMeta):
                def bar(self) -> None: ...
        """)
        errors = [
            'f.pyi:2: error: Class pkg.Foo has abstract attributes "bar"  [misc]'
        ]
        result = self.fixer(src, errors)
        self.assertEqual(result.count("metaclass=abc.ABCMeta"), 1)

    def test_extracts_unqualified_class_name(self):
        src = textwrap.dedent("""\
            class Credentials:
                def refresh(self) -> None: ...
        """)
        errors = [
            "f.pyi:1: error: Class google.oauth2._async.Credentials "
            'has abstract attributes "_perform_refresh_token"  [misc]'
        ]
        result = self.fixer(src, errors)
        self.assertIn("metaclass=abc.ABCMeta", result)
