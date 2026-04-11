from unittest import TestCase

from stub_adder.transformer.file_fix.long_literal_fixer import LongLiteralFixer


class TestLongLiteralFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = LongLiteralFixer()

    def test_applicable_with_y053(self):
        self.assertTrue(
            self.fixer.is_applicable(
                [
                    "file.pyi:11:35: Y053 String and bytes literals >50 characters long are not permitted"
                ]
            )
        )

    def test_not_applicable_without_y053(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: F401 'os' imported but unused"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestLongLiteralFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = LongLiteralFixer()
        self.errors = [
            "file.pyi:1:35: Y053 String and bytes literals >50 characters long are not permitted"
        ]

    def test_no_y053_unchanged(self):
        src = 'X = "short"\n'
        self.assertEqual(self.fixer(src, []), src)

    def test_replaces_long_string(self):
        long_str = "x" * 51
        src = f'ENDPOINT = "{long_str}"\n'
        result = self.fixer(src, self.errors)
        self.assertNotIn(long_str, result)
        self.assertIn("...", result)

    def test_short_string_unchanged(self):
        src = 'X = "short string"\n'
        result = self.fixer(src, self.errors)
        self.assertIn('"short string"', result)

    def test_replaces_long_bytes(self):
        long_val = "x" * 51
        src = f'DATA = b"{long_val}"\n'
        result = self.fixer(src, self.errors)
        self.assertNotIn(long_val, result)
        self.assertIn("...", result)

    def test_multiple_long_literals(self):
        long_a = "a" * 51
        long_b = "b" * 51
        src = f'A = "{long_a}"\nB = "{long_b}"\n'
        result = self.fixer(src, self.errors)
        self.assertNotIn(long_a, result)
        self.assertNotIn(long_b, result)

    def test_type_is_long_literal(self):
        self.assertEqual(self.fixer.type, "long_literal")
