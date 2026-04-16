"""Regression test for LSP arg-type fix where the supertype uses a module-attribute
annotation (e.g. ``_credentials.Signing``), matching the real error:

    output/google/auth/_jwt_async.pyi:50: error: Argument 1 of
    "from_signing_credentials" is incompatible with supertype
    "google.auth.jwt.Credentials"; supertype defines the argument type as "Signing"
"""

import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.multifile_fixes._lsp_violation_fixer import (
    LspViolationFixer,
)


class TestLspSigningResolution(TestCase):
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

    def _setup_stubs(self) -> Path:
        """Create stubs matching the real google-auth structure."""
        self._write("google/__init__.pyi", "")
        self._write("google/auth/__init__.pyi", "")
        # Real Signing definition
        self._write(
            "google/auth/credentials.pyi",
            """\
            class Signing:
                def sign_bytes(self, message: bytes) -> bytes: ...
        """,
        )
        # Async subtype — narrower than Signing
        self._write(
            "google/auth/credentials_async.pyi",
            """\
            from google.auth.credentials import Signing
            class AsyncSigning(Signing): ...
        """,
        )
        # Supertype stub — uses `_credentials.Signing` attribute annotation
        self._write(
            "google/auth/jwt.pyi",
            """\
            from google.auth import credentials as _credentials
            class Credentials(_credentials.Signing):
                @classmethod
                def from_signing_credentials(
                    cls,
                    credentials: '_credentials.Signing',
                    audience: str,
                ) -> 'Credentials': ...
        """,
        )
        # File being fixed — uses narrower AsyncSigning (LSP violation)
        return self._write(
            "google/auth/_jwt_async.pyi",
            """\
            import google.auth.jwt as jwt
            from google.auth import credentials_async as _credentials_async
            class Credentials(jwt.Credentials):
                @classmethod
                def from_signing_credentials(
                    cls,
                    credentials: _credentials_async.AsyncSigning,
                    audience: str,
                ) -> 'Credentials': ...
        """,
        )

    def test_resolves_signing_via_supertype_stub(self):
        """LspViolationFixer sets arg to bare `Signing`; resolve_annotation_imports
        must find it by inspecting jwt.pyi which uses `_credentials.Signing`.
        """
        pyi = self._setup_stubs()

        error = (
            f'{pyi}:6: error: Argument 1 of "from_signing_credentials" '
            'is incompatible with supertype "google.auth.jwt.Credentials"; '
            'supertype defines the argument type as "Signing"  [override]'
        )

        result = LspViolationFixer()._fix_file(
            contents=pyi.read_text(),
            errors=[error],
            stubs_dir=self.root,
        )

        self.assertIn("from google.auth.credentials import Signing", result)
        self.assertIn("credentials: Signing", result)

    def test_verified_by_mypy(self):
        """After the fix, mypy reports no [override] arg error."""
        pyi = self._setup_stubs()

        def _mypy_arg_errors() -> list[str]:
            r = subprocess.run(
                ["mypy", "--strict", str(pyi)],
                capture_output=True,
                text=True,
                env={**os.environ, "MYPYPATH": str(self.root)},
            )
            return [
                line
                for line in r.stdout.splitlines()
                if "from_signing_credentials" in line and "error:" in line
            ]

        before = _mypy_arg_errors()
        self.assertTrue(before, "Expected override error before fix")

        all_errors = subprocess.run(
            ["mypy", "--strict", str(pyi)],
            capture_output=True,
            text=True,
            env={**os.environ, "MYPYPATH": str(self.root)},
        ).stdout.splitlines()

        fixed = LspViolationFixer()._fix_file(
            contents=pyi.read_text(),
            errors=[line for line in all_errors if str(pyi) in line],
            stubs_dir=self.root,
        )
        pyi.write_text(fixed)

        after = _mypy_arg_errors()
        self.assertFalse(
            after,
            "Expected no from_signing_credentials override errors after fix:\n"
            + "\n".join(after),
        )
