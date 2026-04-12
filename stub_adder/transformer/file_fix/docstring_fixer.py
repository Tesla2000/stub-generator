import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import DocstringRange
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

        # Collect DocstringRange for each docstring node.
        # only=True means the docstring is the sole statement — replace with `...`.
        ranges: list[DocstringRange] = []

        body_infos: list[tuple[list[ast.stmt], bool]] = [
            (tree.body, len(tree.body) == 1)
        ]
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                body_infos.append((node.body, len(node.body) == 1))

        for body, only in body_infos:
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                assert first.end_lineno is not None
                ranges.append(
                    DocstringRange(first.lineno, first.end_lineno, only)
                )

        # Process in reverse order so earlier line numbers stay valid.
        for r in sorted(ranges, reverse=True):
            indent = re.match(r"^(\s*)", lines[r.start - 1]).group(1)  # type: ignore[union-attr]
            if r.only:
                lines[r.start - 1 : r.end] = [indent + "...\n"]
            else:
                del lines[r.start - 1 : r.end]

        return "".join(lines)
