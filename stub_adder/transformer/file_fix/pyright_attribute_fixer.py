import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Literal

from stub_adder.transformer.file_fix._base import ManualFix


class PyrightAttributeFixer(ManualFix):
    """Fix pyright reportAttributeAccessIssue errors caused by namespace packages.

    When code does ``import google`` and uses ``google.auth.X``, pyright reports
    ``"auth" is not a known attribute of module "google"``.  The fix is to add
    an explicit ``import google.auth`` (or whatever sub-package is missing).
    """

    type: Literal["pyright_attribute"] = "pyright_attribute"
    _ATTR_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: "(?P<attr>[^"]+)" is not a known attribute of module "(?P<module>[^"]+)"'
        r"(?: \(reportAttributeAccessIssue\))?"
    )

    @staticmethod
    def _missing_submodule_imports(errors: list[str]) -> list[str]:
        """Return ``import X.Y`` statements needed to satisfy attribute errors."""
        imports: list[str] = []
        seen: set[str] = set()
        for error in errors:
            m = PyrightAttributeFixer._ATTR_RE.search(error)
            if not m:
                continue
            submodule = f"{m.group('module')}.{m.group('attr')}"
            if submodule not in seen:
                seen.add(submodule)
                imports.append(f"import {submodule}")
        return imports

    @staticmethod
    def _already_imported(tree: ast.Module) -> set[str]:
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._ATTR_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        new_imports = self._missing_submodule_imports(errors)
        if not new_imports:
            return contents

        tree = ast.parse(contents)
        already = self._already_imported(tree)
        to_add = [
            imp
            for imp in new_imports
            if imp.removeprefix("import ") not in already
        ]
        if not to_add:
            return contents

        return "\n".join(to_add) + "\n" + contents
