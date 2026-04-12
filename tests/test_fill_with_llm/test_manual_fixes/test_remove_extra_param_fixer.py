import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.remove_extra_param_fixer import (
    RemoveExtraParamFixer,
)


def _err(func: str, param: str, kind: str = "") -> str:
    prefix = f"{kind} " if kind else ""
    return (
        f"error: {func} is inconsistent, runtime does not have "
        f'{prefix}parameter "{param}"'
    )


class TestRemoveExtraParamFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = RemoveExtraParamFixer()

    def test_applicable_regular(self):
        self.assertTrue(
            self.fixer.is_applicable([_err("mod.Foo.method", "x")])
        )

    def test_applicable_vararg(self):
        self.assertTrue(
            self.fixer.is_applicable([_err("mod.Foo.method", "args", "*args")])
        )

    def test_applicable_kwarg(self):
        self.assertTrue(
            self.fixer.is_applicable(
                [_err("mod.Foo.method", "kwargs", "**kwargs")]
            )
        )

    def test_not_applicable(self):
        self.assertFalse(self.fixer.is_applicable(["error: unrelated"]))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestRemoveExtraParamFixerRegular(TestCase):
    def setUp(self) -> None:
        self.fixer = RemoveExtraParamFixer()

    def test_removes_named_param(self):
        src = "def foo(x: int, y: str) -> None: ..."
        result = self.fixer(src, [_err("mod.foo", "x")])
        self.assertNotIn("x: int", result)
        self.assertIn("y: str", result)

    def test_removes_param_with_default(self):
        src = "def foo(x: int, y: str = 'hi') -> None: ..."
        result = self.fixer(src, [_err("mod.foo", "y")])
        self.assertNotIn("y", result)
        self.assertIn("x: int", result)

    def test_no_matching_errors_unchanged(self):
        src = "def foo(x: int) -> None: ..."
        self.assertEqual(self.fixer(src, []), src)

    def test_type_is_remove_extra_param(self):
        self.assertEqual(self.fixer.type, "remove_extra_param")


class TestRemoveExtraParamFixerVararg(TestCase):
    def setUp(self) -> None:
        self.fixer = RemoveExtraParamFixer()

    def test_removes_vararg(self):
        src = "def foo(x: int, *args: Any, **kwargs: Any) -> None: ..."
        result = self.fixer(src, [_err("mod.foo", "args", "*args")])
        self.assertNotIn("*args", result)
        self.assertIn("x: int", result)
        self.assertIn("**kwargs", result)

    def test_removes_vararg_from_method(self):
        src = textwrap.dedent("""\
            class Request:
                async def __call__(
                    self,
                    url: str,
                    method: str = 'GET',
                    *args: Any,
                    **kwargs: Any,
                ) -> None: ...
        """)
        result = self.fixer(
            src, [_err("mod.aiohttp.Request.__call__", "args", "*args")]
        )
        self.assertNotIn("*args", result)
        self.assertIn("url: str", result)
        self.assertIn("**kwargs", result)

    def test_removes_kwarg(self):
        src = "def foo(x: int, *args: Any, **kwargs: Any) -> None: ..."
        result = self.fixer(src, [_err("mod.foo", "kwargs", "**kwargs")])
        self.assertNotIn("**kwargs", result)
        self.assertIn("*args", result)
        self.assertIn("x: int", result)

    def test_removes_vararg_and_kwarg_together(self):
        src = "def foo(x: int, *args: Any, **kwargs: Any) -> None: ..."
        errors = [
            _err("mod.foo", "args", "*args"),
            _err("mod.foo", "kwargs", "**kwargs"),
        ]
        result = self.fixer(src, errors)
        self.assertNotIn("*args", result)
        self.assertNotIn("**kwargs", result)
        self.assertIn("x: int", result)

    def test_vararg_only_no_kwarg(self):
        src = "def foo(*args: Any) -> None: ..."
        result = self.fixer(src, [_err("mod.foo", "args", "*args")])
        self.assertNotIn("*args", result)

    def test_full_aiohttp_case(self):
        src = textwrap.dedent("""\
            from typing import Any
            from collections.abc import Mapping
            class Request:
                async def __call__(
                    self,
                    url: str,
                    method: str = 'GET',
                    body: bytes | None = None,
                    headers: Mapping[str, str] | None = None,
                    timeout: float | Any = ...,
                    *args: Any,
                    **kwargs: Any,
                ) -> None: ...
        """)
        result = self.fixer(
            src,
            [
                _err(
                    "google.auth.aio.transport.aiohttp.Request.__call__",
                    "args",
                    "*args",
                )
            ],
        )
        self.assertNotIn("*args", result)
        self.assertIn("**kwargs", result)
        self.assertIn("timeout: float | Any", result)
