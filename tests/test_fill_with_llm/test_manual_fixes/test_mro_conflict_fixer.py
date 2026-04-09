import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.file_fix.mro_conflict_fixer import MroConflictFixer


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


class TestMroConflictFixer(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_errors_unchanged(self):
        src = "class Foo: ...\n"
        self.assertEqual(MroConflictFixer()(src, []), src)

    def test_ignores_non_misc_errors(self):
        src = textwrap.dedent("""\
            class A:
                def go(self) -> None: ...
            class B(A): ...
        """)
        errors = [
            'f.pyi:2: error: Argument 1 of "go" incompatible  [override]'
        ]
        self.assertEqual(MroConflictFixer()(src, errors), src)

    def test_adds_assignment_for_conflict(self):
        src = textwrap.dedent("""\
            class Foo1:
                def before_request(self) -> None: ...
            class Foo2:
                def before_request(self) -> None: ...
            class Foo(Foo1, Foo2): ...
        """)
        errors = [
            'f.pyi:5: error: Definition of "before_request" in base class "Foo1" '
            'is incompatible with definition in base class "Foo2"  [misc]'
        ]
        result = MroConflictFixer()(src, errors)
        self.assertIn("before_request = Foo2.before_request", result)

    def test_only_adds_to_class_with_both_bases(self):
        src = textwrap.dedent("""\
            class Foo1:
                def go(self) -> None: ...
            class Foo2:
                def go(self) -> None: ...
            class Unrelated(Foo1): ...
            class Target(Foo1, Foo2): ...
        """)
        errors = [
            'f.pyi:6: error: Definition of "go" in base class "Foo1" '
            'is incompatible with definition in base class "Foo2"  [misc]'
        ]
        result = MroConflictFixer()(src, errors)
        self.assertIn("go = Foo2.go", result)
        # Unrelated should not get the assignment
        tree_src = result
        self.assertEqual(tree_src.count("go = Foo2.go"), 1)

    def test_does_not_duplicate_existing_assignment(self):
        src = textwrap.dedent("""\
            class Foo1:
                def go(self) -> None: ...
            class Foo2:
                def go(self) -> None: ...
            class Foo(Foo1, Foo2):
                go = Foo2.go
        """)
        errors = [
            'f.pyi:6: error: Definition of "go" in base class "Foo1" '
            'is incompatible with definition in base class "Foo2"  [misc]'
        ]
        result = MroConflictFixer()(src, errors)
        self.assertEqual(result.count("go = Foo2.go"), 1)

    def test_multiple_conflicts_same_class(self):
        src = textwrap.dedent("""\
            class A:
                def foo(self) -> None: ...
                def bar(self) -> None: ...
            class B:
                def foo(self) -> None: ...
                def bar(self) -> None: ...
            class C(A, B): ...
        """)
        errors = [
            'f.pyi:7: error: Definition of "foo" in base class "A" '
            'is incompatible with definition in base class "B"  [misc]',
            'f.pyi:7: error: Definition of "bar" in base class "A" '
            'is incompatible with definition in base class "B"  [misc]',
        ]
        result = MroConflictFixer()(src, errors)
        self.assertIn("foo = B.foo", result)
        self.assertIn("bar = B.bar", result)

    def test_verified_by_mypy(self):
        """Full round-trip: fixer resolves the [misc] error verified by mypy."""

        pyi = self.tmp / "mro_test.pyi"
        stub = textwrap.dedent("""\
            from typing import Any, Coroutine

            class Foo1:
                def before_request(self) -> None | Coroutine[Any, Any, None]: ...
            class Foo2:
                async def before_request(self) -> None: ...
            class Foo(Foo1, Foo2): ...
        """)
        pyi.write_text(stub)

        errors = _mypy_errors(pyi)
        misc_errors = [e for e in errors if "[misc]" in e]
        self.assertTrue(misc_errors, "Expected [misc] errors before fix")

        fixed = MroConflictFixer()(stub, errors)
        pyi.write_text(fixed)

        remaining = [e for e in _mypy_errors(pyi) if "[misc]" in e]
        self.assertFalse(
            remaining,
            "Expected no [misc] errors after fix, got:\n"
            + "\n".join(remaining),
        )


class TestMroConflictFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = MroConflictFixer()

    def test_applicable_with_mro_error(self):
        errors = [
            'f.pyi:1: error: Definition of "foo" in base class "A" is incompatible with definition in base class "B"  [misc]'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_mro_error(self):
        errors = ['f.pyi:1: error: Name "Foo" is not defined  [name-defined]']
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))
