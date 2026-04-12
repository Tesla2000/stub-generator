import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix
from stub_adder.transformer.file_fix._base import SourceSpan


class MutableDefaultFixer(ManualFix):
    """Fix ruff B008 / flake8-pyi Y011: replace mutable/call defaults with ``...``.

    In stubs, argument defaults carry no runtime meaning, so any default
    flagged by B008 or Y011 can safely become ``...``.
    The error location (line:col) is used to identify exactly which default
    to replace, rather than replacing every call-type default blindly.
    """

    type: Literal["mutable_default"] = "mutable_default"
    _B008_RE: ClassVar[re.Pattern[str]] = re.compile(r"\b(B008|Y011)\b")
    # Matches "file.pyi:line:col: CODE ..." and captures line and col (1-based).
    _LOC_RE: ClassVar[re.Pattern[str]] = re.compile(
        r":(\d+):(\d+): (?:B008|Y011)\b"
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._B008_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not self.is_applicable(errors):
            return contents

        # Parse (0-based line, 0-based col) from every B008/Y011 error.
        locations: list[tuple[int, int]] = []
        for error in errors:
            m = self._LOC_RE.search(error)
            if m:
                locations.append((int(m.group(1)) - 1, int(m.group(2)) - 1))

        if not locations:
            return contents

        lines = contents.splitlines(keepends=True)
        tree = ast.parse(contents)

        # Build a map from (0-based line, 0-based col) → end_col for every
        # default node (function args and class-level assignments).
        span_by_loc: dict[tuple[int, int], int] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_defaults = [
                    *node.args.defaults,
                    *(d for d in node.args.kw_defaults if d is not None),
                ]
                for default in all_defaults:
                    key = (default.lineno - 1, default.col_offset)
                    assert default.end_col_offset is not None
                    span_by_loc[key] = default.end_col_offset
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                val = node.value
                key = (val.lineno - 1, val.col_offset)
                assert val.end_col_offset is not None
                span_by_loc[key] = val.end_col_offset
            elif isinstance(node, ast.Assign):
                val = node.value
                key = (val.lineno - 1, val.col_offset)
                assert val.end_col_offset is not None
                span_by_loc[key] = val.end_col_offset

        # Replace in reverse order (rightmost first) to keep offsets valid.
        replacements: list[SourceSpan] = []
        for lineno, col in locations:
            end_col = span_by_loc.get((lineno, col))
            if end_col is not None:
                replacements.append(SourceSpan(lineno, col, end_col))

        replacements.sort(reverse=True)
        for r in replacements:
            line = lines[r.lineno]
            lines[r.lineno] = line[: r.start] + "..." + line[r.end :]

        return "".join(lines)
