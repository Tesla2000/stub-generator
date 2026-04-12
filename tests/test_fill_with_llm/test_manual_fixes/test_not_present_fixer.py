import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.not_present_fixer import (
    NotPresentAtRuntimeFixer,
)


def _err_missing(name: str) -> str:
    return (
        f"error: {name} is not present at runtime\n"
        f"Stub: some definition\n"
        f"Runtime:\n"
        f"MISSING"
    )


def _err_type_alias_any(name: str) -> str:
    return (
        f"error: {name} is not present at runtime\n"
        f"Stub: in file stub.pyi:1\n"
        f"Type alias for Any\n"
        f"Runtime:\n"
        f"MISSING"
    )


class TestNotPresentFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = NotPresentAtRuntimeFixer()

    def test_applicable(self):
        self.assertTrue(self.fixer.is_applicable([_err_missing("mod.Foo")]))

    def test_not_applicable(self):
        self.assertFalse(self.fixer.is_applicable(["error: unrelated"]))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestNotPresentFixerRemoval(TestCase):
    def setUp(self) -> None:
        self.fixer = NotPresentAtRuntimeFixer()

    def test_removes_top_level_function(self):
        src = textwrap.dedent("""\
            def foo() -> None: ...
            def bar() -> None: ...
        """)
        result = self.fixer(src, [_err_missing("mod.foo")])
        self.assertNotIn("def foo", result)
        self.assertIn("def bar", result)

    def test_removes_top_level_class(self):
        src = textwrap.dedent("""\
            class Foo: ...
            class Bar: ...
        """)
        result = self.fixer(src, [_err_missing("mod.Foo")])
        self.assertNotIn("class Foo", result)
        self.assertIn("class Bar", result)

    def test_no_matching_errors_unchanged(self):
        src = "def foo() -> None: ..."
        self.assertEqual(self.fixer(src, []), src)


class TestNotPresentFixerTypeAliasAny(TestCase):
    def setUp(self) -> None:
        self.fixer = NotPresentAtRuntimeFixer()

    def _src(self, body: str) -> str:
        return textwrap.dedent(body).strip()

    def test_removes_type_alias_definition(self):
        src = self._src("""
            from typing import Any, TypeAlias
            ClientTimeout: TypeAlias = Any
            def foo() -> None: ...
        """)
        result = self.fixer(src, [_err_type_alias_any("mod.ClientTimeout")])
        self.assertNotIn("ClientTimeout: TypeAlias", result)
        self.assertIn("def foo", result)

    def test_replaces_usage_with_any(self):
        src = self._src("""
            from typing import Any, TypeAlias
            ClientTimeout: TypeAlias = Any
            def request(timeout: float | ClientTimeout = ...) -> None: ...
        """)
        result = self.fixer(
            src, [_err_type_alias_any("mod.aiohttp.ClientTimeout")]
        )
        self.assertNotIn("ClientTimeout", result)
        self.assertIn("float | Any", result)

    def test_replaces_usage_in_annotation(self):
        src = self._src("""
            from typing import Any, TypeAlias
            MyType: TypeAlias = Any
            class Foo:
                def method(self, x: MyType) -> MyType: ...
        """)
        result = self.fixer(src, [_err_type_alias_any("mod.MyType")])
        self.assertNotIn("MyType", result)
        self.assertIn("x: Any", result)
        self.assertIn("-> Any", result)

    def test_full_aiohttp_stub_case(self):
        src = self._src("""
            from collections.abc import AsyncGenerator, Mapping
            from typing import Any, TypeAlias
            from google.auth.aio import transport
            ClientTimeout: TypeAlias = Any
            class Request(transport.Request):
                async def __call__(
                    self,
                    url: str,
                    timeout: float | ClientTimeout = ...,
                ) -> transport.Response: ...
        """)
        result = self.fixer(
            src,
            [
                _err_type_alias_any(
                    "google.auth.aio.transport.aiohttp.ClientTimeout"
                )
            ],
        )
        self.assertNotIn("ClientTimeout", result)
        self.assertIn("float | Any", result)

    def test_type_alias_any_not_treated_as_removal(self):
        # Ensure it doesn't remove usages as undefined names — it replaces them
        src = self._src("""
            from typing import Any, TypeAlias
            T: TypeAlias = Any
            x: T
        """)
        result = self.fixer(src, [_err_type_alias_any("mod.T")])
        self.assertNotIn("T: TypeAlias", result)
        self.assertIn("x: Any", result)

    def test_type_is_not_present_at_runtime(self):
        self.assertEqual(self.fixer.type, "not_present_at_runtime")
