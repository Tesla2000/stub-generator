import ast
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class DuplicateImportRemover(ProcessBase):
    type: Literal["duplicate_import_remover"] = "duplicate_import_remover"

    def process(self, pyi_paths: list[Path]) -> None:
        for path in pyi_paths:
            original = path.read_text()
            fixed = _remove_duplicates(original)
            if fixed != original:
                path.write_text(fixed)


def _remove_duplicates(contents: str) -> str:
    tree = ast.parse(contents)
    replacements: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        seen: set[tuple[str, str | None]] = set()
        unique: list[ast.alias] = []
        has_dup = False
        for alias in node.names:
            key = (alias.name, alias.asname)
            if key in seen:
                has_dup = True
            else:
                seen.add(key)
                unique.append(alias)
        if not has_dup or node.end_lineno is None:
            continue
        module = "." * node.level + (node.module or "")
        names_str = ", ".join(
            f"{a.name} as {a.asname}" if a.asname else a.name for a in unique
        )
        replacements.append(
            (
                node.lineno,
                node.end_lineno,
                f"from {module} import {names_str}\n",
            )
        )
    if not replacements:
        return contents
    lines = contents.splitlines(keepends=True)
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start - 1 : end] = [replacement]
    return "".join(lines)
