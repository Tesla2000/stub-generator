from unittest import TestCase

from stub_added.transformer.stub_postprocessor import postprocess_stub


class TestPostprocessStub(TestCase):
    def test_formats_with_black(self):
        ugly = "def foo(x:int)->str:\n    ...\n"
        result = postprocess_stub(ugly)
        self.assertIn("def foo(x: int) -> str:", result)

    def test_removes_unused_import(self):
        src = "import os\nimport sys\n\ndef foo() -> None: ...\n"
        result = postprocess_stub(src)
        self.assertNotIn("import os", result)
        self.assertNotIn("import sys", result)

    def test_preserves_used_import(self):
        src = "from pathlib import Path\n\ndef foo() -> Path: ...\n"
        result = postprocess_stub(src)
        self.assertIn("from pathlib import Path", result)

    def test_already_clean_is_idempotent(self):
        src = "def foo(x: int) -> str: ...\n"
        first = postprocess_stub(src)
        second = postprocess_stub(first)
        self.assertEqual(first, second)

    def test_sorts_imports(self):
        src = "import sys\nimport os\n\ndef foo() -> os.PathLike: ...\n"
        result = postprocess_stub(src)
        import_lines = [
            line for line in result.splitlines() if line.startswith("import")
        ]
        self.assertEqual(import_lines, sorted(import_lines))


class TestAnnotationFixer(TestCase):
    def test_args_without_annotation_becomes_any(self):
        src = "def foo(*args, **kwargs) -> None: ...\n"
        result = postprocess_stub(src)
        self.assertIn("*args: Any", result)
        self.assertIn("**kwargs: Any", result)

    def test_args_with_annotation_unchanged(self):
        src = "def foo(*args: int, **kwargs: str) -> None: ...\n"
        result = postprocess_stub(src)
        self.assertIn("*args: int", result)
        self.assertIn("**kwargs: str", result)

    def test_object_param_replaced_with_any(self):
        src = "def foo(x: object) -> None: ...\n"
        result = postprocess_stub(src)
        self.assertIn("x: Any", result)
        self.assertNotIn("x: object", result)

    def test_object_return_replaced_with_any(self):
        src = "def foo() -> object: ...\n"
        result = postprocess_stub(src)
        self.assertIn("-> Any", result)
        self.assertNotIn("-> object", result)

    def test_object_ann_assign_replaced_with_any(self):
        src = "x: object\n"
        result = postprocess_stub(src)
        self.assertIn("x: Any", result)

    def test_any_imported_when_added(self):
        src = "def foo(*args) -> None: ...\n"
        result = postprocess_stub(src)
        self.assertIn("Any", result)

    def test_mixed_args_and_object(self):
        src = "def foo(x: object, *args, **kwargs) -> object: ...\n"
        result = postprocess_stub(src)
        self.assertNotIn("object", result)
        self.assertIn("x: Any", result)
        self.assertIn("*args: Any", result)
        self.assertIn("**kwargs: Any", result)
        self.assertIn("-> Any", result)
