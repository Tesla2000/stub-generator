from unittest import TestCase

from stub_adder.transformer.file_fix.int_float_fixer import IntFloatFixer


class TestIntFloatFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = IntFloatFixer()

    def test_applicable_with_y041(self):
        self.assertTrue(
            self.fixer.is_applicable(
                ['file.pyi:76:27: Y041 Use "float" instead of "int | float"']
            )
        )

    def test_not_applicable_without_y041(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: F401 'os' imported but unused"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestIntFloatFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = IntFloatFixer()
        self.errors = [
            'file.pyi:1:1: Y041 Use "float" instead of "int | float"'
        ]

    def test_no_y041_unchanged(self):
        src = "def foo(x: float) -> None: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_replaces_int_pipe_float(self):
        src = "def foo(x: int | float) -> None: ...\n"
        result = self.fixer(src, self.errors)
        self.assertIn("x: float", result)
        self.assertNotIn("int | float", result)

    def test_replaces_float_pipe_int(self):
        src = "def foo(x: float | int) -> None: ...\n"
        result = self.fixer(src, self.errors)
        self.assertIn("x: float", result)
        self.assertNotIn("float | int", result)

    def test_replaces_union_int_float(self):
        src = "from typing import Union\ndef foo(x: Union[int, float]) -> None: ...\n"
        result = self.fixer(src, self.errors)
        self.assertIn("x: float", result)
        self.assertNotIn("Union[int, float]", result)

    def test_replaces_union_float_int(self):
        src = "from typing import Union\ndef foo(x: Union[float, int]) -> None: ...\n"
        result = self.fixer(src, self.errors)
        self.assertIn("x: float", result)
        self.assertNotIn("Union[float, int]", result)

    def test_replaces_multiple_occurrences(self):
        src = "def foo(x: int | float, y: int | float) -> int | float: ...\n"
        result = self.fixer(src, self.errors)
        self.assertNotIn("int | float", result)
        self.assertEqual(result.count("float"), 3)

    def test_type_is_int_float(self):
        self.assertEqual(self.fixer.type, "int_float")
