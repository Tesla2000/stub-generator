import textwrap
from unittest import TestCase

from stub_adder.transformer.file_fix.remove_default_fixer import (
    RemoveDefaultFixer,
)

_ERROR = (
    'error: {func} is inconsistent, stub parameter "{param}" has a default value'
    " but runtime parameter does not"
)


def _err(func: str, param: str) -> str:
    return _ERROR.format(func=func, param=param)


class TestRemoveDefaultFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = RemoveDefaultFixer()

    def test_applicable(self):
        self.assertTrue(
            self.fixer.is_applicable([_err("some.module.Foo.__init__", "x")])
        )

    def test_not_applicable(self):
        self.assertFalse(self.fixer.is_applicable(["error: unrelated error"]))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestRemoveDefaultFixerRegularFunction(TestCase):
    def setUp(self) -> None:
        self.fixer = RemoveDefaultFixer()

    def test_removes_default_from_regular_function(self):
        src = "def foo(x: int = 5) -> None: ..."
        result = self.fixer(src, [_err("some.module.foo", "x")])
        self.assertNotIn("= 5", result)
        self.assertIn("x: int", result)

    def test_removes_only_named_param(self):
        src = "def foo(x: int = 5, y: str = 'hi') -> None: ..."
        result = self.fixer(src, [_err("module.foo", "x")])
        self.assertNotIn("x: int = 5", result)
        self.assertIn("y: str", result)
        self.assertIn("'hi'", result)

    def test_no_matching_errors_unchanged(self):
        src = "def foo(x: int = 5) -> None: ..."
        self.assertEqual(self.fixer(src, []), src)

    def test_kwonly_default_removed(self):
        src = "def foo(*, x: int = 5) -> None: ..."
        result = self.fixer(src, [_err("module.foo", "x")])
        self.assertNotIn("= 5", result)

    def test_type_is_remove_default(self):
        self.assertEqual(self.fixer.type, "remove_default")


class TestRemoveDefaultFixerDataclass(TestCase):
    def setUp(self) -> None:
        self.fixer = RemoveDefaultFixer()

    def _src(self, body: str) -> str:
        return textwrap.dedent(body).strip()

    def test_removes_field_default_from_dataclass(self):
        src = self._src("""
            from dataclasses import dataclass
            @dataclass
            class Foo:
                x: int
                y: str = 'hello'
        """)
        result = self.fixer(src, [_err("module.Foo.__init__", "y")])
        self.assertNotIn("= 'hello'", result)
        self.assertIn("y: str", result)
        self.assertIn("x: int", result)

    def test_removes_none_default_from_frozen_dataclass(self):
        src = self._src("""
            from dataclasses import dataclass
            @dataclass(frozen=True)
            class AuthenticatorAssertionResponse:
                client_data_json: str
                authenticator_data: str
                signature: str
                user_handle: str | None = None
        """)
        result = self.fixer(
            src,
            [
                _err(
                    "google.oauth2.webauthn_types.AuthenticatorAssertionResponse.__init__",
                    "user_handle",
                )
            ],
        )
        self.assertNotIn("= None", result)
        self.assertIn("user_handle: str | None", result)
        self.assertIn("client_data_json: str", result)

    def test_leaves_other_fields_untouched(self):
        src = self._src("""
            from dataclasses import dataclass
            @dataclass
            class Bar:
                a: int = 1
                b: str = 'keep'
                c: float = 3.0
        """)
        result = self.fixer(src, [_err("module.Bar.__init__", "a")])
        self.assertNotIn("a: int = 1", result)
        self.assertIn("b: str = 'keep'", result)
        self.assertIn("c: float = 3.0", result)

    def test_explicit_init_not_touched_by_dataclass_path(self):
        # Class has explicit __init__ — the function transformer handles it,
        # not the dataclass field transformer.
        src = self._src("""
            from dataclasses import dataclass
            @dataclass
            class Baz:
                x: int = 5
                def __init__(self, x: int = 5) -> None: ...
        """)
        result = self.fixer(src, [_err("module.Baz.__init__", "x")])
        # The explicit __init__ default is removed
        self.assertNotIn("def __init__(self, x: int = 5)", result)
        # The field annotation default is preserved (explicit __init__ takes precedence)
        self.assertIn("x: int = 5", result)

    def test_non_dataclass_class_not_affected(self):
        # Regular class with __init__: should go through function path
        src = self._src("""
            class Plain:
                def __init__(self, x: int = 5) -> None: ...
        """)
        result = self.fixer(src, [_err("module.Plain.__init__", "x")])
        self.assertNotIn("x: int = 5", result)

    def test_multiple_dataclass_fields_multiple_errors(self):
        src = self._src("""
            from dataclasses import dataclass
            @dataclass
            class Multi:
                a: int = 1
                b: str = 'hi'
                c: float = 2.0
        """)
        errors = [
            _err("mod.Multi.__init__", "a"),
            _err("mod.Multi.__init__", "b"),
        ]
        result = self.fixer(src, errors)
        self.assertNotIn("a: int = 1", result)
        self.assertNotIn("b: str = 'hi'", result)
        self.assertIn("c: float = 2.0", result)

    def test_two_dataclasses_independent(self):
        src = self._src("""
            from dataclasses import dataclass
            @dataclass
            class A:
                x: int = 1
            @dataclass
            class B:
                y: str = 'keep'
        """)
        result = self.fixer(src, [_err("mod.A.__init__", "x")])
        self.assertNotIn("x: int = 1", result)
        self.assertIn("y: str = 'keep'", result)
