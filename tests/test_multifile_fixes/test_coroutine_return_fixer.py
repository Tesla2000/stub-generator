import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_added.transformer.multifile_fixes._coroutine_return_fixer import (
    CoroutineReturnFixer,
)


def _make_errors(path: Path, lines: list[str]) -> dict[Path, list[str]]:
    return {path: [f"{path}:{i + 1}: {line}" for i, line in enumerate(lines)]}


class TestParseFixes(TestCase):
    def test_parses_coroutine_override_error(self):
        errors = {
            Path("out/pkg/sub.pyi"): [
                'out/pkg/sub.pyi:5: error: Return type "Coroutine[Any, Any, None]" '
                'of "refresh" incompatible with return type "None" '
                'in supertype "pkg.base.Base"  [override]'
            ]
        }
        result = CoroutineReturnFixer._parse_fixes(errors)
        self.assertEqual(
            result, {("pkg.base.Base", "refresh"): "Coroutine[Any, Any, None]"}
        )

    def test_ignores_non_coroutine_errors(self):
        errors = {
            Path("out/pkg/sub.pyi"): [
                'out/pkg/sub.pyi:5: error: Argument 1 of "foo" incompatible  [override]'
            ]
        }
        self.assertEqual(CoroutineReturnFixer._parse_fixes(errors), {})

    def test_first_occurrence_wins(self):
        errors = {
            Path("out/a.pyi"): [
                'out/a.pyi:1: error: Return type "Coroutine[Any, Any, None]" '
                'of "go" incompatible with return type "None" '
                'in supertype "pkg.Base"  [override]',
                'out/a.pyi:2: error: Return type "Coroutine[Any, Any, int]" '
                'of "go" incompatible with return type "int" '
                'in supertype "pkg.Base"  [override]',
            ]
        }
        result = CoroutineReturnFixer._parse_fixes(errors)
        self.assertEqual(
            result[("pkg.Base", "go")], "Coroutine[Any, Any, None]"
        )

    def test_multiple_methods_and_supertypes(self):
        errors = {
            Path("out/a.pyi"): [
                'out/a.pyi:1: error: Return type "Coroutine[Any, Any, None]" '
                'of "refresh" incompatible with return type "None" '
                'in supertype "pkg.base.Base"  [override]',
                'out/a.pyi:2: error: Return type "Coroutine[Any, Any, int]" '
                'of "compute" incompatible with return type "int" '
                'in supertype "pkg.other.Other"  [override]',
            ]
        }
        result = CoroutineReturnFixer._parse_fixes(errors)
        self.assertIn(("pkg.base.Base", "refresh"), result)
        self.assertIn(("pkg.other.Other", "compute"), result)


class TestFindStubForModule(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_finds_sibling_module(self):
        # out/pkg/sub/child.pyi exists, looking for pkg.base
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "sub").mkdir()
        base = self.root / "pkg" / "base.pyi"
        base.write_text("")
        reference = self.root / "pkg" / "sub" / "child.pyi"
        reference.write_text("")

        result = CoroutineReturnFixer._find_stub_for_module(
            "pkg.base", reference
        )
        self.assertEqual(result, base)

    def test_returns_none_when_not_found(self):
        reference = self.root / "pkg" / "sub.pyi"
        result = CoroutineReturnFixer._find_stub_for_module(
            "pkg.missing", reference
        )
        self.assertIsNone(result)


class TestCoroutineReturnFixer(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, rel: str, content: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content))
        return path

    def test_widens_return_type_in_parent(self):
        parent = self._write(
            "pkg/base.pyi",
            """\
            class Base:
                def refresh(self) -> None: ...
        """,
        )
        child = self._write(
            "pkg/aio/sub.pyi",
            """\
            from pkg.base import Base
            class Sub(Base):
                async def refresh(self) -> None: ...
        """,
        )

        errors = {
            child: [
                f'{child}:2: error: Return type "Coroutine[Any, Any, None]" '
                'of "refresh" incompatible with return type "None" '
                'in supertype "pkg.base.Base"  [override]'
            ]
        }
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )

        result = parent.read_text()
        self.assertIn("Coroutine", result)
        self.assertIn("None", result)
        # return type should be a union
        self.assertIn("|", result)

    def test_adds_typing_imports(self):
        parent = self._write(
            "pkg/base.pyi",
            """\
            class Base:
                def refresh(self) -> None: ...
        """,
        )
        child = self._write(
            "pkg/aio/sub.pyi",
            """\
            from pkg.base import Base
            class Sub(Base):
                async def refresh(self) -> None: ...
        """,
        )
        errors = {
            child: [
                f'{child}:2: error: Return type "Coroutine[Any, Any, None]" '
                'of "refresh" incompatible with return type "None" '
                'in supertype "pkg.base.Base"  [override]'
            ]
        }
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )

        result = parent.read_text()
        self.assertIn("from typing import", result)
        self.assertIn("Coroutine", result)
        self.assertIn("Any", result)

    def test_does_not_duplicate_existing_imports(self):
        parent = self._write(
            "pkg/base.pyi",
            """\
            from typing import Any, Coroutine
            class Base:
                def refresh(self) -> None: ...
        """,
        )
        child = self._write(
            "pkg/aio/sub.pyi",
            """\
            from pkg.base import Base
            class Sub(Base):
                async def refresh(self) -> None: ...
        """,
        )
        errors = {
            child: [
                f'{child}:2: error: Return type "Coroutine[Any, Any, None]" '
                'of "refresh" incompatible with return type "None" '
                'in supertype "pkg.base.Base"  [override]'
            ]
        }
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )

        result = parent.read_text()
        self.assertEqual(result.count("from typing import"), 1)

    def test_no_errors_leaves_parent_unchanged(self):
        parent = self._write(
            "pkg/base.pyi",
            """\
            class Base:
                def refresh(self) -> None: ...
        """,
        )
        original = parent.read_text()
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file={},
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        self.assertEqual(parent.read_text(), original)

    def test_callable_assignment_widens_parent_method(self):
        """[assignment] error: Callable[..., Coroutine] vs Callable[..., X] in base."""
        parent = self._write(
            "pkg/base.pyi",
            """\
            class Base:
                def before_request(self) -> None: ...
        """,
        )
        child = self._write(
            "pkg/aio.pyi",
            """\
            from pkg.base import Base
            class Sub(Base):
                before_request = Base.before_request
        """,
        )
        errors = {
            child: [
                f"{child}:3: error: Incompatible types in assignment "
                '(expression has type "Callable[[], Coroutine[Any, Any, None]]", '
                'base class "Base" defined the type as "Callable[[], None]")  [assignment]'
            ]
        }
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        result = parent.read_text()
        self.assertIn("Coroutine", result)
        self.assertIn("|", result)

    def test_callable_assignment_requires_coroutine_in_expression(self):
        """Does not trigger when expression type does not contain Coroutine."""
        parent = self._write(
            "pkg/base.pyi",
            """\
            class Base:
                def go(self) -> None: ...
        """,
        )
        original = parent.read_text()
        child = self._write(
            "pkg/sub.pyi",
            """\
            from pkg.base import Base
            class Sub(Base):
                go = Base.go
        """,
        )
        errors = {
            child: [
                f"{child}:3: error: Incompatible types in assignment "
                '(expression has type "Callable[[], int]", '
                'base class "Base" defined the type as "Callable[[], None]")  [assignment]'
            ]
        }
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        self.assertEqual(parent.read_text(), original)

    def test_propagates_widening_up_chain(self):
        """Widening a parent that itself has a narrower grandparent propagates up."""
        self._write("pkg/__init__.pyi", "")
        self._write("pkg/aio/__init__.pyi", "")
        grandparent = self._write(
            "pkg/grand.pyi",
            """\
            class GrandBase:
                def refresh(self) -> None: ...
        """,
        )
        parent = self._write(
            "pkg/base.pyi",
            """\
            from pkg.grand import GrandBase
            class Base(GrandBase):
                def refresh(self) -> None: ...
        """,
        )
        child = self._write(
            "pkg/aio/sub.pyi",
            """\
            from pkg.base import Base
            class Sub(Base):
                async def refresh(self) -> None: ...
        """,
        )
        errors = {
            child: [
                f'{child}:2: error: Return type "Coroutine[Any, Any, None]" '
                'of "refresh" incompatible with return type "None" '
                'in supertype "pkg.base.Base"  [override]'
            ]
        }
        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )

        # Both parent and grandparent should be widened
        self.assertIn("Coroutine", parent.read_text())
        self.assertIn("Coroutine", grandparent.read_text())

    def test_verified_by_mypy_end_to_end(self):
        """Full round-trip: fixer resolves the [override] error verified by mypy."""

        self._write("mypkg/__init__.pyi", "")
        self._write(
            "mypkg/base.pyi",
            """\
            class Base:
                def refresh(self) -> None: ...
        """,
        )
        child = self._write(
            "mypkg/aio.pyi",
            """\
            from mypkg.base import Base
            class AsyncSub(Base):
                async def refresh(self) -> None: ...
        """,
        )

        def mypy_override_errors() -> list[str]:
            r = subprocess.run(
                ["mypy", "--strict", str(child)],
                capture_output=True,
                text=True,
                env={**__import__("os").environ, "MYPYPATH": str(self.root)},
            )
            return [
                line for line in r.stdout.splitlines() if "[override]" in line
            ]

        before = mypy_override_errors()
        self.assertTrue(before, "Expected [override] errors before fix")

        r = subprocess.run(
            ["mypy", "--strict", str(child)],
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "MYPYPATH": str(self.root)},
        )
        real_errors = {
            child: [
                line for line in r.stdout.splitlines() if str(child) in line
            ]
        }

        CoroutineReturnFixer()(
            affected_stubs=[],
            errors_by_file=real_errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )

        remaining = mypy_override_errors()
        self.assertFalse(
            remaining,
            "Expected no [override] errors after fix, got:\n"
            + "\n".join(remaining),
        )


class TestCoroutineReturnFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = CoroutineReturnFixer()

    def test_applicable_with_return_incompatible_error(self):
        errors = [
            'f.pyi:5: error: Return type "Coroutine[Any, Any, None]" of "foo" '
            'incompatible with return type "None" in supertype "pkg.Base"  [override]'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_applicable_with_assignment_error(self):
        errors = [
            "f.pyi:3: error: Incompatible types in assignment "
            '(expression has type "Callable[[str], Coroutine[Any, Any, None]]", '
            'base class "Base" defined the type as "Callable[[str], None]")'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_coroutine_error(self):
        errors = ['f.pyi:1: error: Name "Foo" is not defined  [name-defined]']
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))

    def test_not_applicable_for_non_coroutine_return_override(self):
        """Plain return type override (no Coroutine) belongs to LspViolationFixer."""
        errors = [
            'f.pyi:1: error: Return type "str" of "foo" incompatible with '
            'return type "int" in supertype "Base"  [override]'
        ]
        self.assertFalse(self.fixer.is_applicable(errors))
