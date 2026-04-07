import ast
import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_added.transformer._class_finder import find_name_in_supertype_stubs
from stub_added.transformer.file_fix import ImportFixer


def _mypy_errors(path: Path) -> list[str]:
    result = subprocess.run(
        ["mypy", "--strict", str(path)],
        capture_output=True,
        text=True,
    )
    return [
        line
        for line in result.stdout.splitlines()
        if line.startswith(str(path) + ":")
    ]


class TestFindNameInSupertypeStubs(TestCase):
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

    def test_finds_class_directly_defined_in_supertype_stub(self):
        """When the supertype stub defines `class Response` directly, return that module."""
        self._write(
            "pkg/transport/__init__.pyi",
            """\
            class Response: ...
            class Request: ...
            """,
        )
        result = find_name_in_supertype_stubs(
            "Response", ["pkg.transport"], self.root
        )
        self.assertEqual(result, "pkg.transport")

    def test_finds_class_via_annotation_attribute(self):
        """When supertype uses `mod.Name` annotation, resolves through the alias."""
        self._write("pkg/creds.pyi", "class Signing: ...")
        self._write(
            "pkg/jwt.pyi",
            """\
            from pkg import creds as _creds
            class Credentials:
                def sign(self, c: '_creds.Signing') -> None: ...
            """,
        )
        result = find_name_in_supertype_stubs(
            "Signing", ["pkg.jwt"], self.root
        )
        self.assertEqual(result, "pkg.creds")

    def test_returns_none_when_not_found(self):
        self._write("pkg/transport/__init__.pyi", "class Request: ...")
        result = find_name_in_supertype_stubs(
            "Response", ["pkg.transport"], self.root
        )
        self.assertIsNone(result)

    def test_returns_none_when_stub_missing(self):
        result = find_name_in_supertype_stubs(
            "Response", ["nonexistent.module"], self.root
        )
        self.assertIsNone(result)


class TestResolveAnnotationImportsViaSupertypeStub(TestCase):
    """Regression: LspViolationFixer sets return type to bare `Response` (from error
    message); resolve_annotation_imports must find it in the supertype stub.

    Replicates the real failure in google/auth/transport/_aiohttp_requests.pyi:
      Return type "Coroutine[Any, Any, _Response]" of "__call__" incompatible with
      return type "Response" in supertype "google.auth.transport.Request"  [override]
    """

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

    def test_resolves_response_from_supertype_stub(self):
        """After LspViolationFixer rewrites return to `Response`, the import must
        be found via the supertype stub that defines `class Response`."""
        self._write(
            "pkg/transport/__init__.pyi",
            """\
            class Response: ...
            class Request:
                def __call__(self, url: str) -> Response: ...
            """,
        )
        # Code as it looks after LspViolationFixer ran: `Response` bare, not imported
        code = textwrap.dedent("""\
            from pkg import transport

            class _MyResponse(transport.Response):
                def data(self) -> bytes: ...

            class MyRequest(transport.Request):
                def __call__(self, url: str) -> Response: ...
        """)
        errors = [
            'f.pyi:6: error: Return type "Coroutine[Any, Any, _MyResponse]" of "__call__" '
            'incompatible with return type "Response" in supertype "pkg.transport.Request"  [override]'
        ]
        result = ImportFixer.resolve_annotation_imports(
            code, errors, self.root
        )
        self.assertIn("from pkg.transport import Response", result)

    def test_locally_defined_class_not_flagged_as_unresolved(self):
        """A class defined in the same file used as a return type must not raise.

        Regression: google/auth/transport/_aiohttp_requests.pyi defines `_Response`
        and uses it as the return type of `request()`. Without the locally-defined
        names exclusion, resolve_annotation_imports raises RuntimeError for `_Response`.
        """
        self._write(
            "pkg/transport/__init__.pyi",
            """\
            class Response: ...
            class Request:
                def __call__(self, url: str) -> Response: ...
            """,
        )
        # _Response is defined locally; Response is imported via the fix
        code = textwrap.dedent("""\
            from pkg.transport import Response
            from pkg import transport

            class _Response(transport.Response):
                def data(self) -> bytes: ...

            class Request(transport.Request):
                def __call__(self, url: str) -> Response: ...

            class Session:
                async def request(self, url: str) -> _Response: ...
        """)
        errors = [
            'f.pyi:7: error: Return type "Coroutine[Any, Any, _Response]" of "__call__" '
            'incompatible with return type "Response" in supertype "pkg.transport.Request"  [override]'
        ]
        # Must not raise even though `_Response` is in annotation names and not imported
        result = ImportFixer.resolve_annotation_imports(
            code, errors, self.root
        )
        self.assertNotIn("import _Response", result)

    def test_raises_when_type_cannot_be_resolved(self):
        """If no strategy finds the type, RuntimeError is raised."""
        code = textwrap.dedent("""\
            def foo(x: UnknownType) -> None: ...
        """)
        errors = [
            'f.pyi:1: error: Argument 1 of "foo" incompatible with supertype '
            '"nonexistent.module.Base"  [override]'
        ]
        with self.assertRaises(RuntimeError):
            ImportFixer.resolve_annotation_imports(code, errors, self.root)


class TestLocallyDefinedNames(TestCase):
    def _parse(self, src: str) -> ast.Module:
        return ast.parse(textwrap.dedent(src))

    def test_collects_class_names(self):
        tree = self._parse("class Foo: ...\nclass Bar: ...\n")
        self.assertEqual(
            ImportFixer._locally_defined_names(tree), {"Foo", "Bar"}
        )

    def test_collects_function_names(self):
        tree = self._parse(
            "def foo() -> None: ...\nasync def bar() -> None: ...\n"
        )
        self.assertEqual(
            ImportFixer._locally_defined_names(tree), {"foo", "bar"}
        )

    def test_collects_annotated_assignments(self):
        tree = self._parse("x: int\ny: str\n")
        self.assertEqual(ImportFixer._locally_defined_names(tree), {"x", "y"})

    def test_collects_plain_assignments(self):
        tree = self._parse("x = 1\ny = 2\n")
        self.assertEqual(ImportFixer._locally_defined_names(tree), {"x", "y"})

    def test_does_not_collect_nested_names(self):
        """Names defined inside a class body are not module-level."""
        tree = self._parse("class Foo:\n    class Bar: ...\n")
        self.assertEqual(ImportFixer._locally_defined_names(tree), {"Foo"})

    def test_empty_module(self):
        tree = self._parse("")
        self.assertEqual(ImportFixer._locally_defined_names(tree), set())


class TestImportFixer(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_name_defined_errors_unchanged(self):
        src = "def foo(x: int) -> str: ...\n"
        self.assertEqual(ImportFixer()(src, []), src)

    def test_adds_typeshed_import_for_name_defined_error(self):
        src = textwrap.dedent("""\
            def foo(x: SupportsItems[str, str]) -> None: ...
        """)
        errors = [
            'f.pyi:1: error: Name "SupportsItems" is not defined  [name-defined]'
        ]
        result = ImportFixer()(src, errors)
        self.assertIn("from _typeshed import SupportsItems", result)

    def test_adds_supertype_module_import_for_name_defined_error(self):
        src = textwrap.dedent("""\
            def foo(x: PreparedRequest) -> None: ...
        """)
        errors = [
            'f.pyi:1: error: Name "PreparedRequest" is not defined  [name-defined]',
            'f.pyi:1: error: Signature of "foo" incompatible with supertype "requests.adapters.HTTPAdapter"  [override]',
        ]
        result = ImportFixer()(src, errors)
        self.assertIn("PreparedRequest", result)
        self.assertIn("from requests", result)

    def test_verified_by_mypy(self):
        pyi = self.tmp_path / "imports.pyi"
        stub = textwrap.dedent("""\
            from requests.adapters import HTTPAdapter

            class Sub(HTTPAdapter):
                def send(
                    self,
                    request: PreparedRequest,
                    stream: bool = ...,
                    timeout: float | None = ...,
                    verify: bool | str = ...,
                    cert: str | tuple[str, str] | None = ...,
                    proxies: Mapping[str, str] | None = ...,
                ) -> Response: ...
        """)
        pyi.write_text(stub)

        errors = _mypy_errors(pyi)
        name_errors = [e for e in errors if "[name-defined]" in e]
        self.assertTrue(
            name_errors, "Expected [name-defined] errors before fix"
        )

        fixed = ImportFixer()(stub, errors)
        pyi.write_text(fixed)

        remaining = [e for e in _mypy_errors(pyi) if "[name-defined]" in e]
        self.assertFalse(
            remaining,
            "Expected no [name-defined] errors after fix, got:\n"
            + "\n".join(remaining),
        )


class TestImportFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = ImportFixer()

    def test_applicable_with_name_defined_error(self):
        errors = ['f.pyi:1: error: Name "Foo" is not defined  [name-defined]']
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_name_defined(self):
        errors = [
            'f.pyi:1: error: Signature of "foo" incompatible with supertype "Base"  [override]'
        ]
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))
