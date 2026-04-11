from unittest import TestCase

from stub_adder.transformer.file_fix.type_alias_fixer import TypeAliasFixer


class TestTypeAliasFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = TypeAliasFixer()

    def test_applicable_with_y026(self):
        errors = [
            'file.pyi:6:1: Y026 Use typing_extensions.TypeAlias for type aliases, e.g. "ClientTimeout: TypeAlias = Any"'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_y026(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: F401 'os' imported but unused"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestTypeAliasFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = TypeAliasFixer()

    def _y026(self, name: str) -> list[str]:
        return [
            f'file.pyi:1:1: Y026 Use typing_extensions.TypeAlias for type aliases, e.g. "{name}: TypeAlias = Any"'
        ]

    def test_no_y026_unchanged(self):
        src = "X: TypeAlias = int\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_adds_typealias_annotation(self):
        src = "from typing import Any\n\nClientTimeout = Any\n"
        result = self.fixer(src, self._y026("ClientTimeout"))
        self.assertIn("ClientTimeout: TypeAlias = Any", result)

    def test_adds_typing_extensions_import(self):
        src = "from typing import Any\n\nFoo = Any\n"
        result = self.fixer(src, self._y026("Foo"))
        self.assertIn("from typing_extensions import TypeAlias", result)

    def test_does_not_duplicate_typealias_import(self):
        src = "from typing_extensions import TypeAlias\nfrom typing import Any\n\nFoo = Any\n"
        result = self.fixer(src, self._y026("Foo"))
        self.assertEqual(result.count("TypeAlias"), 2)  # import + annotation

    def test_only_rewrites_named_variable(self):
        src = "Bar = int\nFoo = str\n"
        result = self.fixer(src, self._y026("Foo"))
        self.assertIn("Foo: TypeAlias = str", result)
        self.assertNotIn("Bar: TypeAlias", result)

    def test_type_is_type_alias(self):
        self.assertEqual(self.fixer.type, "type_alias")
