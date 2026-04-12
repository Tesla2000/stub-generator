import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix
from stub_adder.transformer.file_fix._base import SourceSpan

_TYPING_EXTENSIONS_SELF = "from typing_extensions import Self"
_CLASS_RE: re.Pattern[str] = re.compile(
    r'"__enter__" methods in classes like "(?P<cls>\w+)"'
)


class EnterReturnSelfFixer(ManualFix):
    """Fix flake8-pyi Y034: ``__enter__`` should return ``Self`` not the class name.

    Rewrites ``def __enter__(self) -> ClassName: ...`` to
    ``def __enter__(self) -> Self: ...`` and adds
    ``from typing_extensions import Self`` if not already present.
    """

    type: Literal["enter_return_self"] = "enter_return_self"
    _Y034_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bY034\b")

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._Y034_RE.search(e) for e in errors)

    @staticmethod
    def _affected_classes(errors: list[str]) -> set[str]:
        classes: set[str] = set()
        for error in errors:
            m = _CLASS_RE.search(error)
            if m:
                classes.add(m.group("cls"))
        return classes

    @staticmethod
    def _has_self_import(tree: ast.Module) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in ("typing_extensions", "typing"):
                    for alias in node.names:
                        if alias.name == "Self":
                            return True
        return False

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._Y034_RE.search(e) for e in errors):
            return contents

        affected = self._affected_classes(errors)
        if not affected:
            return contents

        tree = ast.parse(contents)
        lines = contents.splitlines(keepends=True)

        spans: list[SourceSpan] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name not in affected:
                continue
            for item in ast.walk(node):
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "__enter__"
                    and item.returns is not None
                ):
                    ret = item.returns
                    assert ret.end_col_offset is not None
                    spans.append(
                        SourceSpan(
                            ret.lineno - 1, ret.col_offset, ret.end_col_offset
                        )
                    )

        for span in sorted(spans, reverse=True):
            line = lines[span.lineno]
            lines[span.lineno] = line[: span.start] + "Self" + line[span.end :]

        result = "".join(lines)

        if spans and not self._has_self_import(tree):
            result = _TYPING_EXTENSIONS_SELF + "\n" + result

        return result
