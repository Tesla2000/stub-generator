"""Regression tests for the two ways `Signer` (or any aliased/attribute-accessed class)
can become unresolvable after LspViolationFixer rewrites a property return type.

Case 1 – alias import stripped by autoimport
  The file has ``from pkg.crypt import Signer as _Signer``.  LspViolationFixer
  replaces *all* ``signer`` properties with ``-> Signer``, so ``_Signer`` is no
  longer referenced and autoimport removes that import.  The pre-autoimport tree
  must be used as a fallback import-hint source.

Case 2 – dotted attribute annotation, no from-import
  The file has ``import pkg.crypt`` and a parameter typed
  ``signer: pkg.crypt.Signer | None``.  LspViolationFixer introduces bare
  ``Signer`` as a return type; the pre-autoimport tree's own annotation
  attribute expressions must be scanned to locate the module.
"""

import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_adder.transformer.multifile_fixes._lsp_violation_fixer import (
    LspViolationFixer,
)


def _write(base: Path, rel: str, content: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


class TestResolveSignerViaAliasImport(TestCase):
    """Case 1: alias ``_Signer`` import is stripped by autoimport after the
    fixer replaces all occurrences of ``_Signer`` with bare ``Signer``.
    The pre-autoimport tree still carries the alias hint; resolution must
    follow it to the real module.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # crypt/__init__.pyi re-exports via assignment (not a class def)
        _write(self.root, "pkg/crypt/__init__.pyi", "Signer = base.Signer\n")
        _write(self.root, "pkg/crypt/base.pyi", "class Signer: ...\n")
        # Minimal supertype with the Signing interface
        _write(
            self.root,
            "pkg/credentials.pyi",
            """\
            from pkg.crypt import Signer as _Signer
            class Signing:
                @property
                def signer(self) -> _Signer: ...
            """,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_errors(self, pyi: Path) -> list[str]:
        return [
            f'{pyi}:10: error: Signature of "signer" incompatible with supertype "Signing"  [override]',
            f"{pyi}:10: note:      Superclass:",
            f"{pyi}:10: note:          Signer",
            f"{pyi}:10: note:      Subclass:",
            f"{pyi}:10: note:          object",
        ]

    def test_resolve_signer_when_alias_stripped(self) -> None:
        """After the fixer removes the only use of ``_Signer``, autoimport drops
        the alias import.  The pre-autoimport tree fallback must still find
        ``Signer`` in ``pkg.crypt.base``.
        """
        pyi = _write(
            self.root,
            "pkg/impl.pyi",
            """\
            from pkg.crypt import Signer as _Signer
            from pkg import credentials

            class Base(credentials.Signing):
                @property
                def signer(self) -> _Signer: ...

            class Sub(credentials.Signing):
                @property
                def signer(self) -> object: ...
            """,
        )
        result = LspViolationFixer()._fix_file(
            contents=pyi.read_text(),
            errors=self._make_errors(pyi),
            stubs_dir=self.root,
        )
        self.assertIn("Signer", result)
        self.assertNotIn(
            "object", result.split("def signer")[1].split("\n")[0]
        )


class TestResolveSignerViaAnnotationAttribute(TestCase):
    """Case 2: the file has a dotted-attribute annotation ``pkg.crypt.Signer``
    in a parameter but only a module-level ``import pkg.crypt`` (no from-import).
    After the fixer introduces bare ``Signer``, the annotation-attribute scan
    must locate the module.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root, "pkg/crypt/__init__.pyi", "Signer = base.Signer\n")
        _write(self.root, "pkg/crypt/base.pyi", "class Signer: ...\n")
        _write(
            self.root,
            "pkg/credentials.pyi",
            """\
            class Signing:
                @property
                def signer(self) -> object: ...
            """,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_errors(self, pyi: Path) -> list[str]:
        return [
            f'{pyi}:10: error: Signature of "signer" incompatible with supertype "Signing"  [override]',
            f"{pyi}:10: note:      Superclass:",
            f"{pyi}:10: note:          Signer",
            f"{pyi}:10: note:      Subclass:",
            f"{pyi}:10: note:          object",
        ]

    def test_resolve_signer_via_attribute_annotation(self) -> None:
        """The file uses ``pkg.crypt.Signer`` only as a dotted attribute in a
        parameter annotation, not as a from-import.  The annotation-attribute
        scan must find the module for bare ``Signer``.
        """
        pyi = _write(
            self.root,
            "pkg/impl.pyi",
            """\
            import pkg.crypt
            from pkg import credentials

            class IDTokenCredentials(credentials.Signing):
                def __init__(
                    self,
                    signer: pkg.crypt.Signer | None = None,
                ) -> None: ...
                @property
                def signer(self) -> object: ...
            """,
        )
        result = LspViolationFixer()._fix_file(
            contents=pyi.read_text(),
            errors=self._make_errors(pyi),
            stubs_dir=self.root,
        )
        self.assertIn("Signer", result)
        self.assertNotIn(
            "object", result.split("def signer")[1].split("\n")[0]
        )
