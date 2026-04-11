import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix


class MutableDefaultFixer(ManualFix):
    """Fix ruff B008 errors: replace function-call defaults with ``...``.

    In stubs, argument defaults carry no runtime meaning, so any call like
    ``def foo(x: T = SomeClass()) -> None: ...`` can safely become
    ``def foo(x: T = ...) -> None: ...``.
    """

    type: Literal["mutable_default"] = "mutable_default"
    _B008_RE: ClassVar[re.Pattern[str]] = re.compile(r"\b(B008|Y011)\b")

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._B008_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._B008_RE.search(e) for e in errors):
            return contents

        lines = contents.splitlines(keepends=True)
        tree = ast.parse(contents)

        # Collect (line, col_offset, end_col_offset) of every Call node used
        # as a function argument default, in reverse order so replacements
        # don't shift column offsets for later nodes on the same line.
        calls: list[tuple[int, int, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_defaults = [
                    *node.args.defaults,
                    *(d for d in node.args.kw_defaults if d is not None),
                ]
                for default in all_defaults:
                    if isinstance(default, ast.Call):
                        assert default.end_col_offset is not None
                        calls.append(
                            (
                                default.lineno - 1,  # 0-based
                                default.col_offset,
                                default.end_col_offset,
                            )
                        )

        # Sort reverse so we replace from right to left within each line.
        calls.sort(key=lambda t: (t[0], t[1]), reverse=True)

        for lineno, start, end in calls:
            line = lines[lineno]
            lines[lineno] = line[:start] + "..." + line[end:]

        return "".join(lines)
