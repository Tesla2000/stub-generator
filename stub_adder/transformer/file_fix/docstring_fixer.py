import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix


class DocstringFixer(ManualFix):
    """Fix flake8-pyi Y021: remove docstrings from stubs.

    Docstrings (string literals as the first statement of a module, class, or
    function body) are not permitted in stub files.
    """

    type: Literal["docstring"] = "docstring"
    _Y021_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bY021\b")

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._Y021_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._Y021_RE.search(e) for e in errors):
            return contents

        tree = ast.parse(contents)
        lines = contents.splitlines(keepends=True)

        # Collect line ranges of docstring nodes (1-based, inclusive).
        ranges: list[tuple[int, int]] = []
        bodies: list[list[ast.stmt]] = [tree.body]
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                bodies.append(node.body)

        for body in bodies:
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                assert first.end_lineno is not None
                ranges.append((first.lineno, first.end_lineno))

        # Remove in reverse order so earlier line numbers stay valid.
        for start, end in sorted(ranges, reverse=True):
            del lines[start - 1 : end]

        return "".join(lines)
