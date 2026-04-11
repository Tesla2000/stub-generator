import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix

_TYPING_EXTENSIONS_IMPORT = "from typing_extensions import TypeAlias"
_VAR_RE: re.Pattern[str] = re.compile(
    r'Use typing_extensions\.TypeAlias for type aliases, e\.g\. "(?P<name>\w+): TypeAlias'
)


class TypeAliasFixer(ManualFix):
    """Fix flake8-pyi Y026: add TypeAlias annotation to bare type alias assignments.

    ``ClientTimeout = Any`` becomes ``ClientTimeout: TypeAlias = Any`` and
    ``from typing_extensions import TypeAlias`` is added if not already present.
    """

    type: Literal["type_alias"] = "type_alias"
    _Y026_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bY026\b")

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._Y026_RE.search(e) for e in errors)

    @staticmethod
    def _alias_names(errors: list[str]) -> set[str]:
        names: set[str] = set()
        for error in errors:
            m = _VAR_RE.search(error)
            if m:
                names.add(m.group("name"))
        return names

    @staticmethod
    def _has_typealias_import(tree: ast.Module) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in ("typing_extensions", "typing"):
                    for alias in node.names:
                        if alias.name == "TypeAlias":
                            return True
        return False

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._Y026_RE.search(e) for e in errors):
            return contents

        names = self._alias_names(errors)
        if not names:
            return contents

        tree = ast.parse(contents)
        lines = contents.splitlines(keepends=True)

        # Rewrite matching module-level assignments X = <value> → X: TypeAlias = <value>
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in names
            ):
                lineno = node.lineno - 1  # 0-based
                line = lines[lineno]
                name = node.targets[0].id
                # Replace "name = " with "name: TypeAlias = "
                lines[lineno] = line.replace(
                    f"{name} =", f"{name}: TypeAlias =", 1
                )

        result = "".join(lines)

        if not self._has_typealias_import(tree):
            result = _TYPING_EXTENSIONS_IMPORT + "\n" + result

        return result
