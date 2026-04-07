import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_added.transformer.file_fix._base import ManualFix


class _MroConflictResolver(ast.NodeTransformer):
    """Add `method = Base2.method` for each MRO conflict in affected classes."""

    def __init__(self, conflicts: list[tuple[str, str, str]]) -> None:
        # conflicts: [(method, base1, base2), ...]
        self._conflicts = conflicts
        self.changed = False

    @staticmethod
    def _base_name(node: ast.expr) -> str:
        """Return the simple name of a base class expression."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        base_names = {self._base_name(b) for b in node.bases}
        for method, base1, base2 in self._conflicts:
            if base1 not in base_names or base2 not in base_names:
                continue
            # Skip if the assignment already exists
            already = any(
                isinstance(stmt, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == method
                    for t in stmt.targets
                )
                for stmt in node.body
            )
            if already:
                continue
            assignment = ast.Assign(
                targets=[ast.Name(id=method, ctx=ast.Store())],
                value=ast.Attribute(
                    value=ast.Name(id=base2, ctx=ast.Load()),
                    attr=method,
                    ctx=ast.Load(),
                ),
                lineno=0,
                col_offset=0,
            )
            node.body.append(assignment)
            self.changed = True
        self.generic_visit(node)
        return node


class MroConflictFixer(ManualFix):
    type: Literal["mro_conflict"] = "mro_conflict"
    _MRO_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: Definition of "(?P<method>[^"]+)" in base class "(?P<base1>[^"]+)" '
        r'is incompatible with definition in base class "(?P<base2>[^"]+)"'
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._MRO_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        conflicts: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for error in errors:
            m = self._MRO_RE.search(error)
            if not m:
                continue
            key = (m.group("method"), m.group("base1"), m.group("base2"))
            if key not in seen:
                seen.add(key)
                conflicts.append(key)

        if not conflicts:
            return contents

        tree = ast.parse(contents)
        resolver = _MroConflictResolver(conflicts)
        tree = resolver.visit(tree)
        if not resolver.changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
