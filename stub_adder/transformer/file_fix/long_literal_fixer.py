import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Literal

from stub_adder.transformer.file_fix._base import ManualFix, SourceSpan

_MAX_LEN = 50


class LongLiteralFixer(ManualFix):
    """Fix flake8-pyi Y053: replace string/bytes literals >50 chars with ``...``.

    Stub files should not contain long string or bytes literals; they carry no
    useful type information and bloat the file.
    """

    type: Literal["long_literal"] = "long_literal"
    _Y053_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bY053\b")

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._Y053_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._Y053_RE.search(e) for e in errors):
            return contents

        tree = ast.parse(contents)
        lines = contents.splitlines(keepends=True)

        spans: list[SourceSpan] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, (str, bytes))
                and len(node.value) > _MAX_LEN
            ):
                assert node.end_col_offset is not None
                spans.append(
                    SourceSpan(
                        node.lineno - 1, node.col_offset, node.end_col_offset
                    )
                )

        # Replace right-to-left so column offsets stay valid.
        for span in sorted(spans, reverse=True):
            line = lines[span.lineno]
            lines[span.lineno] = line[: span.start] + "..." + line[span.end :]

        return "".join(lines)
