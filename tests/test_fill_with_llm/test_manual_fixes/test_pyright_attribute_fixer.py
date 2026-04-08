import tempfile
import textwrap
from pathlib import Path
from unittest import TestCase

from stub_added.transformer.error_generator._pyright import Pyright
from stub_added.transformer.file_fix.pyright_attribute_fixer import (
    PyrightAttributeFixer,
)


class TestPyrightAttributeFixerIsApplicable(TestCase):
    def setUp(self) -> None:
        self.fixer = PyrightAttributeFixer()

    def test_applicable_with_attribute_error(self):
        errors = [
            'f.pyi:14: error: "auth" is not a known attribute of module "google" (reportAttributeAccessIssue)'
        ]
        self.assertTrue(self.fixer.is_applicable(errors))

    def test_not_applicable_without_attribute_error(self):
        errors = ['f.pyi:1: error: Name "Foo" is not defined  [name-defined]']
        self.assertFalse(self.fixer.is_applicable(errors))

    def test_not_applicable_empty(self):
        self.assertFalse(self.fixer.is_applicable([]))


class TestPyrightAttributeFixer(TestCase):
    def setUp(self) -> None:
        self.fixer = PyrightAttributeFixer()

    def test_no_errors_unchanged(self):
        src = "class Foo: ...\n"
        self.assertEqual(self.fixer(src, []), src)

    def test_adds_submodule_import(self):
        src = textwrap.dedent("""\
            import google

            def foo(request: google.auth.transport.Request) -> None: ...
        """)
        errors = [
            'f.pyi:3: error: "auth" is not a known attribute of module "google" (reportAttributeAccessIssue)'
        ]
        result = self.fixer(src, errors)
        self.assertIn("import google.auth", result)

    def test_does_not_duplicate_existing_import(self):
        src = textwrap.dedent("""\
            import google
            import google.auth

            def foo(request: google.auth.transport.Request) -> None: ...
        """)
        errors = [
            'f.pyi:4: error: "auth" is not a known attribute of module "google" (reportAttributeAccessIssue)'
        ]
        result = self.fixer(src, errors)
        self.assertEqual(result.count("import google.auth"), 1)

    def test_adds_multiple_submodule_imports(self):
        src = textwrap.dedent("""\
            import requests

            class Foo(requests.adapters.HTTPAdapter): ...
            class Bar(requests.sessions.Session): ...
        """)
        errors = [
            'f.pyi:3: error: "adapters" is not a known attribute of module "requests" (reportAttributeAccessIssue)',
            'f.pyi:4: error: "sessions" is not a known attribute of module "requests" (reportAttributeAccessIssue)',
        ]
        result = self.fixer(src, errors)
        self.assertIn("import requests.adapters", result)
        self.assertIn("import requests.sessions", result)

    def test_deduplicates_same_error_multiple_lines(self):
        src = textwrap.dedent("""\
            import google

            def foo(r: google.auth.transport.Request) -> None: ...
            def bar(r: google.auth.transport.Request) -> None: ...
        """)
        errors = [
            'f.pyi:3: error: "auth" is not a known attribute of module "google" (reportAttributeAccessIssue)',
            'f.pyi:4: error: "auth" is not a known attribute of module "google" (reportAttributeAccessIssue)',
        ]
        result = self.fixer(src, errors)
        self.assertEqual(result.count("import google.auth"), 1)

    def test_ignores_non_attribute_errors(self):
        src = "import google\n"
        errors = [
            'f.pyi:1: error: Import "cryptography.hazmat.primitives" could not be resolved (reportMissingImports)'
        ]
        result = self.fixer(src, errors)
        self.assertEqual(result, src)


class TestPyrightAttributeFixerRoundTrip(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fixer = PyrightAttributeFixer()
        self.pyright = Pyright()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    _ATTR_MSG: str = "is not a known attribute of module"

    def _round_trip(self, stub: str, stubs_dir: Path | None = None) -> None:
        pyi = self.tmp / "test_stub.pyi"
        pyi.write_text(stub)
        effective_stubs_dir = stubs_dir or self.tmp

        initial_errors = self.pyright.generate([pyi], effective_stubs_dir).get(
            pyi, []
        )
        self.assertTrue(
            any(self._ATTR_MSG in e for e in initial_errors),
            "Expected attribute-access errors before fix, got:\n"
            + "\n".join(initial_errors),
        )

        # Apply the fixer iteratively (mirrors max_attempts pipeline behaviour)
        contents = stub
        for _ in range(self.fixer.max_attempts):
            errors = self.pyright.generate([pyi], effective_stubs_dir).get(
                pyi, []
            )
            if not any(self._ATTR_MSG in e for e in errors):
                break
            contents = self.fixer(contents, errors)
            pyi.write_text(contents)

        remaining = [
            e
            for e in self.pyright.generate([pyi], effective_stubs_dir).get(
                pyi, []
            )
            if self._ATTR_MSG in e
        ]
        self.assertFalse(
            remaining,
            "Expected no attribute-access errors after fix, got:\n"
            + "\n".join(remaining),
        )

    def test_google_auth_attribute_access(self):
        typeshed = Path(__file__).parents[3] / "typeshed"
        stub = textwrap.dedent("""\
            import google

            class Credentials(google.auth.credentials.Credentials): ...
        """)
        self._round_trip(stub, stubs_dir=typeshed)

    def test_requests_adapters_attribute_access(self):
        stub = textwrap.dedent("""\
            import requests

            class MyAdapter(requests.adapters.BaseAdapter): ...
        """)
        self._round_trip(stub)

    def test_google_auth_transport_with_from_import(self):
        """from google.auth import X does not make google.auth accessible as attribute."""
        typeshed = Path(__file__).parents[3] / "typeshed"
        stub = textwrap.dedent("""\
            from typing import Mapping

            import google
            from google.auth import credentials

            class Credentials(credentials.Credentials):
                token: str

                def __init__(self, token: str) -> None: ...
                @property
                def expired(self) -> bool: ...
                @property
                def valid(self) -> bool: ...
                def refresh(self, request: google.auth.transport.Request) -> None: ...
                def apply(self, headers: Mapping[str, str], token: str | None = None) -> None: ...
                def before_request(
                    self, request: google.auth.transport.Request, method: str, url: str, headers: Mapping[str, str]
                ) -> None: ...
        """)
        self._round_trip(stub, stubs_dir=typeshed)
