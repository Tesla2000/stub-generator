import ast
import re
import textwrap
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Literal

from stub_adder.transformer.file_fix._base import ManualFix


class TypeCheckingFixer(ManualFix):
    """Fix flake8-pyi Y002: unwrap ``if TYPE_CHECKING:`` blocks in stubs.

    In stub files every definition is already for type-checking only, so
    ``if TYPE_CHECKING:`` guards are unnecessary.  This fixer inlines the
    block body and removes ``TYPE_CHECKING`` from imports when it is no
    longer referenced.
    """

    type: Literal["type_checking"] = "type_checking"
    _Y002_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bY002\b")

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._Y002_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._Y002_RE.search(e) for e in errors):
            return contents

        tree = ast.parse(contents)
        lines = contents.splitlines(keepends=True)

        # Collect If nodes whose test is a bare ``TYPE_CHECKING`` name,
        # in reverse order so line-number edits don't shift later nodes.
        blocks: list[tuple[int, int, list[ast.stmt]]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"
                and not node.orelse
            ):
                assert node.end_lineno is not None
                blocks.append((node.lineno, node.end_lineno, node.body))

        if not blocks:
            return contents

        for if_start, if_end, body in sorted(blocks, reverse=True):
            # Extract the body lines and dedent by one level.
            body_lines = lines[
                if_start:if_end
            ]  # if_start is 0-based index = lineno-1+1
            dedented = textwrap.dedent("".join(body_lines))
            # Replace the whole if block (header + body) with the dedented body.
            lines[if_start - 1 : if_end] = list(
                dedented.splitlines(keepends=True)
            )

        result = "".join(lines)

        # Remove TYPE_CHECKING from imports if it is no longer referenced.
        result = self._remove_type_checking_import(result)
        return result

    @staticmethod
    def _remove_type_checking_import(contents: str) -> str:
        """Remove TYPE_CHECKING from import lines if unused elsewhere."""
        # Quick check: if TYPE_CHECKING still appears outside an import, keep it.
        tree = ast.parse(contents)
        uses = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "TYPE_CHECKING"
        )
        imports = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module in ("typing", "typing_extensions")
            and any(a.name == "TYPE_CHECKING" for a in node.names)
        )
        if uses > imports:
            # Still referenced outside import lines — leave it.
            return contents

        # Rewrite the import line(s) that contain TYPE_CHECKING.
        out_lines = []
        for line in contents.splitlines(keepends=True):
            new_line = _drop_name_from_import(line, "TYPE_CHECKING")
            if new_line is not None:
                if new_line.strip():
                    out_lines.append(new_line)
                # else: entire import was only TYPE_CHECKING — drop the line
            else:
                out_lines.append(line)
        return "".join(out_lines)


def _drop_name_from_import(line: str, name: str) -> str | None:
    """Return line with *name* removed from a ``from X import ...`` statement.

    Returns ``None`` if the line does not import *name*.
    Returns an empty string if *name* was the only import on the line.
    """
    # Match: from X import a, TYPE_CHECKING, b  (any order, possible parens)
    m = re.match(
        r"^(\s*from\s+\S+\s+import\s+)(.+?)(\s*)$", line.rstrip("\n\r")
    )
    if not m:
        return None
    prefix, names_part, _ = m.groups()
    has_parens = names_part.startswith("(") and names_part.endswith(")")
    inner = names_part[1:-1].strip() if has_parens else names_part

    names = [n.strip() for n in inner.split(",")]
    if name not in names:
        return None
    names = [n for n in names if n and n != name]
    if not names:
        return ""  # entire import was just this name
    new_names = ", ".join(names)
    if has_parens:
        new_names = f"({new_names})"
    ending = "\n" if line.endswith("\n") else ""
    return f"{prefix}{new_names}{ending}"
