import ast
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_added.transformer._class_finder import find_class_module
from stub_added.transformer.multifile_fixes._any_base_fixer import AnyBaseFixer


def _tree(src: str) -> ast.Module:
    return ast.parse(textwrap.dedent(src))


class TestFindClassModule(TestCase):
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

    def test_finds_class_via_import(self):
        self._write("pkg/base.pyi", "class Signer: ...")
        tree = _tree("from pkg import base\nfrom pkg.base import Signer\n")
        result = find_class_module("Signer", tree, self.root)
        self.assertEqual(result, "pkg.base")

    def test_returns_none_when_missing(self):
        tree = _tree("from pkg import base\nfrom pkg.base import Missing\n")
        result = find_class_module("Missing", tree, self.root)
        self.assertIsNone(result)

    def test_returns_none_when_not_imported(self):
        self._write("pkg/base.pyi", "class Signer: ...")
        tree = _tree("")  # no import of Signer
        result = find_class_module("Signer", tree, self.root)
        self.assertIsNone(result)

    def test_follows_reexport_chain(self):
        # pkg/crypt/__init__.pyi re-exports Signer as Any
        self._write(
            "pkg/crypt/__init__.pyi", "from pkg.crypt.base import Signer\n"
        )
        self._write("pkg/crypt/base.pyi", "class Signer: ...")
        tree = _tree("from pkg.crypt import Signer\n")
        result = find_class_module("Signer", tree, self.root)
        self.assertEqual(result, "pkg.crypt.base")

    def test_finds_class_via_module_attribute(self):
        """Matches real pattern: `from pkg import _credentials; class X(_credentials.Signing)`
        where _credentials.pyi directly defines class Signing (like google.auth._credentials).
        """
        self._write("pkg/_credentials.pyi", "class Signing: ...")
        tree = _tree(
            "from pkg import _credentials\nclass X(_credentials.Signing): ...\n"
        )
        result = find_class_module("Signing", tree, self.root, lineno=2)
        self.assertEqual(result, "pkg._credentials")

    def test_finds_class_via_module_attribute_with_reexport(self):
        """Module attribute + re-export chain: _credentials/__init__ imports from _credentials/base."""
        self._write(
            "pkg/_credentials/__init__.pyi",
            "from pkg._credentials.base import Signing\n",
        )
        self._write("pkg/_credentials/base.pyi", "class Signing: ...")
        tree = _tree(
            "from pkg import _credentials\nclass X(_credentials.Signing): ...\n"
        )
        result = find_class_module("Signing", tree, self.root, lineno=2)
        self.assertEqual(result, "pkg._credentials.base")


class TestAnyBaseFixer(TestCase):
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

    def test_no_errors_unchanged(self):
        pyi = self._write("pkg/sub.pyi", "class Foo: ...\n")
        original = pyi.read_text()
        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file={},
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        self.assertEqual(pyi.read_text(), original)

    def test_replaces_any_base_with_direct_import(self):
        self._write("pkg/crypt/base.pyi", "class Signer: ...")
        self._write(
            "pkg/crypt/__init__.pyi", "from pkg.crypt.base import Signer"
        )
        pyi = self._write(
            "pkg/auth.pyi",
            """\
            from pkg import crypt
            class MySigner(crypt.Signer): ...
        """,
        )
        errors = {
            pyi: [
                f'{pyi}:2: error: Class cannot subclass "Signer" (has type "Any")  [misc]'
            ]
        }
        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        result = pyi.read_text()
        self.assertIn("from pkg.crypt.base import Signer", result)
        self.assertIn("class MySigner(Signer)", result)

    def test_replaces_bare_name_base(self):
        self._write("pkg/crypt/base.pyi", "class Signer: ...")
        self._write(
            "pkg/crypt/__init__.pyi", "from pkg.crypt.base import Signer"
        )
        pyi = self._write(
            "pkg/auth.pyi",
            """\
            from pkg.crypt import Signer
            class MySigner(Signer): ...
        """,
        )
        errors = {
            pyi: [
                f'{pyi}:2: error: Class cannot subclass "Signer" (has type "Any")  [misc]'
            ]
        }
        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        result = pyi.read_text()
        self.assertIn("from pkg.crypt.base import Signer", result)
        self.assertNotIn("from pkg.crypt import Signer", result)

    def test_replaces_same_name_base_with_module_qualified(self):
        """When class Foo(Foo) would collide, use `from pkg import base; class Foo(base.Foo)`."""
        self._write("pkg/crypt/base.pyi", "class Signer: ...")
        self._write(
            "pkg/crypt/__init__.pyi", "from pkg.crypt.base import Signer"
        )
        pyi = self._write(
            "pkg/auth.pyi",
            """\
            from pkg.crypt import Signer
            class Signer(Signer): ...
        """,
        )
        errors = {
            pyi: [
                f'{pyi}:2: error: Class cannot subclass "Signer" (has type "Any")  [misc]'
            ]
        }
        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        result = pyi.read_text()
        self.assertIn("from pkg.crypt import base", result)
        self.assertIn("class Signer(base.Signer)", result)
        self.assertNotIn("from pkg.crypt.base import Signer", result)

    def test_ignores_non_any_misc_errors(self):
        pyi = self._write("pkg/auth.pyi", "class Foo: ...\n")
        original = pyi.read_text()
        errors = {
            pyi: [
                f'{pyi}:1: error: Definition of "go" in base class "A" '
                'is incompatible with definition in base class "B"  [misc]'
            ]
        }
        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        self.assertEqual(pyi.read_text(), original)

    def test_skips_when_class_not_found_in_stubs(self):
        pyi = self._write(
            "pkg/auth.pyi",
            """\
            from external import Signer
            class MySigner(Signer): ...
        """,
        )
        original = pyi.read_text()
        errors = {
            pyi: [
                f'{pyi}:2: error: Class cannot subclass "Signer" (has type "Any")  [misc]'
            ]
        }
        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )
        self.assertEqual(pyi.read_text(), original)

    def test_verified_by_mypy(self):
        self._write("mypkg/__init__.pyi", "")
        self._write("mypkg/crypt/__init__.pyi", "")
        self._write(
            "mypkg/crypt/base.pyi",
            """\
            import abc
            class Signer(metaclass=abc.ABCMeta):
                def sign(self, message: bytes) -> bytes: ...
        """,
        )
        # crypt/__init__.pyi exposes Signer as Incomplete (Any)
        self._write(
            "mypkg/crypt/__init__.pyi",
            """\
            from typing import Any
            Signer: Any
        """,
        )
        pyi = self._write(
            "mypkg/auth.pyi",
            """\
            from mypkg import crypt
            class MySigner(crypt.Signer):
                def sign(self, message: bytes) -> bytes: ...
        """,
        )

        def mypy_misc_errors() -> list[str]:
            r = subprocess.run(
                ["mypy", "--strict", str(pyi)],
                capture_output=True,
                text=True,
                env={**os.environ, "MYPYPATH": str(self.root)},
            )
            return [
                line
                for line in r.stdout.splitlines()
                if 'has type "Any"' in line
            ]

        before = mypy_misc_errors()
        self.assertTrue(before, "Expected 'has type Any' errors before fix")

        errors = {
            pyi: [
                line
                for line in subprocess.run(
                    ["mypy", "--strict", str(pyi)],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "MYPYPATH": str(self.root)},
                ).stdout.splitlines()
                if str(pyi) in line
            ]
        }

        AnyBaseFixer()(
            affected_stubs=[],
            errors_by_file=errors,
            completed={},
            layer_deps={},
            stubs_dir=self.root,
        )

        remaining = mypy_misc_errors()
        self.assertFalse(
            remaining,
            "Expected no 'has type Any' errors after fix, got:\n"
            + "\n".join(remaining),
        )
