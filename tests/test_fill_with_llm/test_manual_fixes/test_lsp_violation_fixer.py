import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.multifile_fixes import (
    LspViolationFixer,
)


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


_MTLS_STUB = textwrap.dedent("""\
    import ssl
    from pathlib import Path
    from typing import Any, Mapping, Optional, Tuple, Union

    from requests import PreparedRequest, Response
    from requests.adapters import HTTPAdapter

    class MdsMtlsAdapter(HTTPAdapter):
        ssl_context: ssl.SSLContext
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...
        def init_poolmanager(self, *args: Any, **kwargs: Any) -> None: ...
        def proxy_manager_for(self, *args: Any, **kwargs: Any) -> None: ...
        def send(
            self,
            request: PreparedRequest,
            stream: bool = ...,
            timeout: bool | str = ...,
            verify: Tuple[bytes, bytes] = ...,
            cert: Union[bytes, str] = ...,
            proxies: Optional[Mapping[str, str]] = ...,
        ) -> Response: ...
""")


class TestLspViolationFixer(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_errors_unchanged(self):
        src = "def foo(x: int) -> str: ...\n"
        self.assertEqual(LspViolationFixer()(src, []), src)

    def test_fixes_override_errors_verified_by_mypy(self):
        pyi = self.tmp_path / "mtls.pyi"
        pyi.write_text(_MTLS_STUB)

        errors = _mypy_errors(pyi)
        override_errors = [e for e in errors if "[override]" in e]
        self.assertTrue(
            override_errors,
            "Expected mypy to report [override] errors in the unfixed stub",
        )

        fixed = LspViolationFixer()(_MTLS_STUB, errors)
        pyi.write_text(fixed)

        remaining = [e for e in _mypy_errors(pyi) if "[override]" in e]
        self.assertFalse(
            remaining,
            "Expected no [override] errors after fix, got:\n"
            + "\n".join(remaining),
        )

    def test_first_supertype_wins(self):
        src = "def send(self, x: int, y: int) -> None: ...\n"
        errors = [
            'f.pyi:1: error: Argument 2 of "send" is incompatible with supertype "A"; '
            'supertype defines the argument type as "str"  [override]',
            'f.pyi:1: error: Argument 2 of "send" is incompatible with supertype "B"; '
            'supertype defines the argument type as "bytes"  [override]',
        ]
        result = LspViolationFixer()(src, errors)
        self.assertIn("str", result)
        self.assertNotIn("bytes", result)

    def test_full_signature_format(self):
        # mypy's newer format: reports full superclass/subclass signatures in notes
        src = (
            "def send(self, request: int, stream: bool, timeout: bool, "
            "verify: str, cert: int) -> None: ...\n"
        )
        errors = [
            'f.pyi:1: error: Signature of "send" incompatible with supertype "Base"  [override]',
            "f.pyi:1: note:      Superclass:",
            "f.pyi:1: note:          def send(self, request: int, stream: bool, timeout: float, verify: bool | str, cert: bytes | str) -> None",
            "f.pyi:1: note:      Subclass:",
            "f.pyi:1: note:          def send(self, request: int, stream: bool, timeout: bool, verify: str, cert: int) -> None",
        ]
        result = LspViolationFixer()(src, errors)
        self.assertIn("timeout: float", result)
        self.assertIn("verify: bool | str", result)
        self.assertIn("cert: bytes | str", result)

    def test_vararg_subclass_gets_full_superclass_signature(self):
        src = "def foo(self, *args: Any, **kwargs: Any) -> None: ...\n"
        errors = [
            'f.pyi:1: error: Signature of "foo" incompatible with supertype "Base"  [override]',
            "f.pyi:1: note:      Superclass:",
            "f.pyi:1: note:          def foo(self, x: int, y: str = ...) -> None",
            "f.pyi:1: note:      Subclass:",
            "f.pyi:1: note:          def foo(self, *args: Any, **kwargs: Any) -> None",
        ]
        result = LspViolationFixer()(src, errors)
        self.assertIn("x: int", result)
        self.assertIn("y: str", result)
        self.assertNotIn("*args", result)
        self.assertNotIn("**kwargs", result)

    def test_adds_imports_for_superclass_types(self):
        # Stub uses *args/**kwargs; superclass note introduces PreparedRequest and
        # Response resolved by searching the supertype module hierarchy.
        src = textwrap.dedent("""\
            from typing import Any
            from requests.adapters import HTTPAdapter

            class Sub(HTTPAdapter):
                def send(self, *args: Any, **kwargs: Any) -> None: ...
        """)
        errors = [
            'f.pyi:5: error: Signature of "send" incompatible with supertype "requests.adapters.HTTPAdapter"  [override]',
            "f.pyi:5: note:      Superclass:",
            "f.pyi:5: note:          def send(self, request: PreparedRequest, stream: bool = ...) -> Response",
            "f.pyi:5: note:      Subclass:",
            "f.pyi:5: note:          def send(self, *args: Any, **kwargs: Any) -> None",
        ]
        result = LspViolationFixer()(src, errors)
        self.assertIn("PreparedRequest", result)
        self.assertIn("Response", result)
        self.assertIn("from requests", result)

    def test_adds_typeshed_imports_for_superclass_types(self):
        # SupportsItems comes from _typeshed (not importable at runtime).
        src = textwrap.dedent("""\
            from typing import Any
            from requests.adapters import HTTPAdapter

            class Sub(HTTPAdapter):
                def send(self, *args: Any, **kwargs: Any) -> None: ...
        """)
        errors = [
            'f.pyi:5: error: Signature of "send" incompatible with supertype "requests.adapters.HTTPAdapter"  [override]',
            "f.pyi:5: note:      Superclass:",
            "f.pyi:5: note:          def send(self, params: SupportsItems[str, str] | None = ...) -> None",
            "f.pyi:5: note:      Subclass:",
            "f.pyi:5: note:          def send(self, *args: Any, **kwargs: Any) -> None",
        ]
        result = LspViolationFixer()(src, errors)
        self.assertIn("SupportsItems", result)
        self.assertIn("from _typeshed import SupportsItems", result)

    def test_adds_imports_verified_by_mypy(self):
        pyi = self.tmp_path / "imports.pyi"
        stub = textwrap.dedent("""\
            from typing import Any
            from requests.adapters import HTTPAdapter

            class Sub(HTTPAdapter):
                def send(self, *args: Any, **kwargs: Any) -> None: ...
        """)
        pyi.write_text(stub)

        errors = _mypy_errors(pyi)
        override_errors = [e for e in errors if "[override]" in e]
        self.assertTrue(
            override_errors, "Expected [override] errors before fix"
        )

        fixed = LspViolationFixer()(stub, errors)
        pyi.write_text(fixed)

        remaining = [e for e in _mypy_errors(pyi) if "[override]" in e]
        self.assertFalse(
            remaining,
            "Expected no [override] errors after fix, got:\n"
            + "\n".join(remaining),
        )

    def test_field_override_ann_assign(self):
        # AnnAssign field where subclass widens the type
        src = textwrap.dedent("""\
            class Base:
                key_id: str
            class Sub(Base):
                key_id: str | None
        """)
        errors = [
            'f.pyi:3: error: Signature of "key_id" incompatible with supertype "Base"  [override]',
            "f.pyi:3: note:      Superclass:",
            "f.pyi:3: note:          str",
            "f.pyi:3: note:      Subclass:",
            "f.pyi:3: note:          str | None",
        ]
        result = LspViolationFixer()(src, errors)
        # Should narrow back to str (superclass type)
        self.assertNotIn("str | None", result)
        self.assertIn("key_id: str", result)

    def test_field_override_property(self):
        # @property where subclass widens the return type
        src = textwrap.dedent("""\
            class Base:
                @property
                def key_id(self) -> str: ...
            class Sub(Base):
                @property
                def key_id(self) -> str | None: ...
        """)
        errors = [
            'f.pyi:5: error: Signature of "key_id" incompatible with supertype "Base"  [override]',
            "f.pyi:5: note:      Superclass:",
            "f.pyi:5: note:          str",
            "f.pyi:5: note:      Subclass:",
            "f.pyi:5: note:          str | None",
        ]
        result = LspViolationFixer()(src, errors)
        self.assertNotIn("str | None", result)
        self.assertIn("-> str", result)

    def test_field_override_verified_by_mypy(self):
        pyi = self.tmp_path / "field_override.pyi"
        stub = textwrap.dedent("""\
            class Base:
                @property
                def key_id(self) -> str: ...
            class Sub(Base):
                @property
                def key_id(self) -> str | None: ...
        """)
        pyi.write_text(stub)

        errors = _mypy_errors(pyi)
        override_errors = [e for e in errors if "[override]" in e]
        self.assertTrue(
            override_errors, "Expected [override] errors before fix"
        )

        fixed = LspViolationFixer()(stub, errors)
        pyi.write_text(fixed)

        remaining = [e for e in _mypy_errors(pyi) if "[override]" in e]
        self.assertFalse(
            remaining,
            "Expected no [override] errors after fix, got:\n"
            + "\n".join(remaining),
        )

    def test_full_signature_format_verified_by_mypy(self):
        pyi = self.tmp_path / "mtls2.pyi"
        # Use swapped cert/verify (wrong types, correct order) to trigger signature error
        stub = textwrap.dedent("""\
            import ssl
            from pathlib import Path
            from typing import Any, Mapping, Optional, Union

            from requests import PreparedRequest, Response
            from requests.adapters import HTTPAdapter

            class MdsMtlsAdapter(HTTPAdapter):
                ssl_context: ssl.SSLContext
                def __init__(self, *args: Any, **kwargs: Any) -> None: ...
                def send(
                    self,
                    request: PreparedRequest,
                    stream: bool = ...,
                    timeout: float | tuple[float, float] | tuple[float, None] | None = ...,
                    verify: bytes | str | tuple[bytes | str, bytes | str] | None = ...,
                    cert: bool | str = ...,
                    proxies: Optional[Mapping[str, str]] = ...,
                ) -> Response: ...
        """)
        pyi.write_text(stub)

        errors = _mypy_errors(pyi)
        override_errors = [e for e in errors if "[override]" in e]
        self.assertTrue(
            override_errors, "Expected [override] errors before fix"
        )

        fixed = LspViolationFixer()(stub, errors)
        pyi.write_text(fixed)

        remaining = [e for e in _mypy_errors(pyi) if "[override]" in e]
        self.assertFalse(
            remaining,
            "Expected no [override] errors after fix, got:\n"
            + "\n".join(remaining),
        )


class TestLspViolationFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = LspViolationFixer()

    def test_applicable_with_override_error(self):
        errors = [
            'f.pyi:1: error: Signature of "foo" incompatible with supertype "Base"  [override]'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_override(self):
        errors = ['f.pyi:1: error: Name "Foo" is not defined  [name-defined]']
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))

    def test_applicable_with_return_override_non_coroutine(self):
        errors = [
            'f.pyi:1: error: Return type "str" of "foo" incompatible with '
            'return type "int" in supertype "Base"  [override]'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_for_coroutine_return_override(self):
        """Coroutine return errors belong to CoroutineReturnFixer, not LspViolationFixer."""
        errors = [
            'f.pyi:5: error: Return type "Coroutine[Any, Any, None]" of "foo" '
            'incompatible with return type "None" in supertype "Base"  [override]'
        ]
        self.assertFalse(self.fixer.is_applicable(errors))
