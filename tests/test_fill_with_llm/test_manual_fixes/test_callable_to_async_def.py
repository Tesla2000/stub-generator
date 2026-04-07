import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_added.transformer.file_fix.callable_to_async_def import (
    CallableToAsyncDef,
)


def _mypy_errors(path: Path, mypypath: str = "") -> list[str]:
    env = os.environ.copy()
    if mypypath:
        env["MYPYPATH"] = mypypath
    result = subprocess.run(
        ["mypy", "--strict", str(path)],
        capture_output=True,
        text=True,
        env=env,
    )
    return [
        line
        for line in result.stdout.splitlines()
        if line.startswith(str(path) + ":")
    ]


class TestCallableToAsyncDef(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_errors_unchanged(self):
        src = "class Foo:\n    def go(self) -> None: ...\n"
        self.assertEqual(CallableToAsyncDef()(src, []), src)

    def test_ignores_non_coroutine_assignment_errors(self):
        src = textwrap.dedent("""\
            class Base:
                def go(self) -> None: ...
            class Sub(Base):
                go = Base.go
        """)
        errors = [
            "f.pyi:4: error: Incompatible types in assignment "
            '(expression has type "Callable[[], int]", '
            'base class "Base" defined the type as "Callable[[], None]")  [assignment]'
        ]
        self.assertEqual(CallableToAsyncDef()(src, errors), src)

    def test_converts_assignment_to_async_def(self):
        src = textwrap.dedent("""\
            class Async:
                async def before_request(self, x: int) -> None: ...
            class Sub(Async):
                before_request = Async.before_request
        """)
        errors = [
            "f.pyi:4: error: Incompatible types in assignment "
            '(expression has type "Callable[[int], Coroutine[Any, Any, None]]", '
            'base class "Base" defined the type as "Callable[[int], None]")  [assignment]'
        ]
        result = CallableToAsyncDef()(src, errors)
        self.assertIn("async def before_request", result)
        self.assertNotIn("before_request = Async.before_request", result)

    def test_preserves_parameter_types(self):
        src = textwrap.dedent("""\
            class Async:
                async def refresh(self, request: str, timeout: int) -> None: ...
            class Sub(Async):
                refresh = Async.refresh
        """)
        errors = [
            "f.pyi:4: error: Incompatible types in assignment "
            '(expression has type "Callable[[str, int], Coroutine[Any, Any, None]]", '
            'base class "Base" defined the type as "Callable[[str, int], None]")  [assignment]'
        ]
        result = CallableToAsyncDef()(src, errors)
        self.assertIn("request: str", result)
        self.assertIn("timeout: int", result)

    def test_multiple_assignments_on_different_lines(self):
        src = textwrap.dedent("""\
            class Async:
                async def foo(self) -> None: ...
                async def bar(self) -> None: ...
            class Sub(Async):
                foo = Async.foo
                bar = Async.bar
        """)
        errors = [
            "f.pyi:5: error: Incompatible types in assignment "
            '(expression has type "Callable[[], Coroutine[Any, Any, None]]", '
            'base class "Base" defined the type as "Callable[[], None]")  [assignment]',
            "f.pyi:6: error: Incompatible types in assignment "
            '(expression has type "Callable[[], Coroutine[Any, Any, None]]", '
            'base class "Base" defined the type as "Callable[[], None]")  [assignment]',
        ]
        result = CallableToAsyncDef()(src, errors)
        self.assertIn("async def foo", result)
        self.assertIn("async def bar", result)

    def test_converts_when_referenced_class_not_in_file(self):
        src = textwrap.dedent("""\
            class Sub:
                go = External.go
        """)
        errors = [
            "f.pyi:2: error: Incompatible types in assignment "
            '(expression has type "Callable[[], Coroutine[Any, Any, None]]", '
            'base class "Base" defined the type as "Callable[[], None]")  [assignment]'
        ]
        # Falls back to building async def from the Callable type in the error
        result = CallableToAsyncDef()(src, errors)
        self.assertIn("async def go", result)
        self.assertNotIn("go = External.go", result)

    def test_verified_by_mypy(self):
        """After conversion, [assignment] error is replaced by fixable [override]."""
        pyi = self.tmp / "cred.pyi"
        stub = textwrap.dedent("""\
            from typing import Any, Coroutine, Mapping

            class Credentials1:
                def before_request(self, x: int) -> None: ...

            class Credentials2:
                async def before_request(self, x: int) -> None: ...

            class AnonCredentials(Credentials1, Credentials2):
                before_request = Credentials2.before_request
        """)
        pyi.write_text(stub)

        before = _mypy_errors(pyi)
        assignment_errors = [
            e for e in before if "[assignment]" in e and "Coroutine" in e
        ]
        self.assertTrue(
            assignment_errors,
            "Expected [assignment] Coroutine errors before fix",
        )

        fixed = CallableToAsyncDef()(stub, before)
        pyi.write_text(fixed)

        remaining = [
            e
            for e in _mypy_errors(pyi)
            if "[assignment]" in e and "Coroutine" in e
        ]
        self.assertFalse(
            remaining,
            "Expected no [assignment] Coroutine errors after fix, got:\n"
            + "\n".join(remaining),
        )
