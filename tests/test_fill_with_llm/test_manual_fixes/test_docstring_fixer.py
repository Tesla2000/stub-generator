import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.docstring_fixer import DocstringFixer

Q = '"""'


class TestDocstringFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = DocstringFixer()

    def test_applicable_with_y021(self):
        self.assertTrue(
            self.fixer.is_applicable(
                [
                    "file.pyi:1:1: Y021 Docstrings should not be included in stubs"
                ]
            )
        )

    def test_not_applicable_without_y021(self):
        self.assertFalse(
            self.fixer.is_applicable(
                ["file.pyi:1:1: F401 'os' imported but unused"]
            )
        )

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestDocstringFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = DocstringFixer()
        self.errors = [
            "file.pyi:1:1: Y021 Docstrings should not be included in stubs"
        ]

    def test_no_y021_unchanged(self):
        src = "def foo() -> None: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_removes_module_docstring(self):
        src = f"{Q}Transport adapter for typing stubs.{Q}\n\nimport abc\n"
        result = self.fixer(src, self.errors)
        self.assertNotIn(Q, result)
        self.assertIn("import abc", result)

    def test_removes_class_docstring(self):
        src = f"class Foo:\n    {Q}A class.{Q}\n\n    x: int\n"
        result = self.fixer(src, self.errors)
        self.assertNotIn("A class.", result)
        self.assertIn("x: int", result)

    def test_removes_function_docstring(self):
        src = f"def foo() -> None:\n    {Q}Does nothing.{Q}\n    ...\n"
        result = self.fixer(src, self.errors)
        self.assertNotIn("Does nothing.", result)
        self.assertIn("def foo", result)

    def test_removes_multiline_docstring(self):
        src = textwrap.dedent(f"""\
            class Bar:
                {Q}
                Multi
                line.
                {Q}

                x: int
        """)
        result = self.fixer(src, self.errors)
        self.assertNotIn("Multi", result)
        self.assertIn("x: int", result)

    def test_removes_multiple_docstrings(self):
        src = f"{Q}Module doc.{Q}\n\nclass Foo:\n    {Q}Class doc.{Q}\n\n    x: int\n"
        result = self.fixer(src, self.errors)
        self.assertNotIn("Module doc", result)
        self.assertNotIn("Class doc", result)
        self.assertIn("x: int", result)

    def test_type_is_docstring(self):
        self.assertEqual(self.fixer.type, "docstring")
