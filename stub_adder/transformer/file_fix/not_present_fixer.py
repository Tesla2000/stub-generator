import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix

_TYPE_CHECK_ONLY = "type_check_only"


class _AddTypeCheckOnly(ast.NodeTransformer):
    """Add @type_check_only decorator to specified classes."""

    def __init__(self, class_names: set[str]) -> None:
        self._names = class_names
        self.changed = False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        if node.name in self._names:
            already = any(
                (isinstance(d, ast.Name) and d.id == _TYPE_CHECK_ONLY)
                or (
                    isinstance(d, ast.Attribute) and d.attr == _TYPE_CHECK_ONLY
                )
                for d in node.decorator_list
            )
            if not already:
                node.decorator_list.insert(
                    0, ast.Name(id=_TYPE_CHECK_ONLY, ctx=ast.Load())
                )
                self.changed = True
        self.generic_visit(node)
        return node


class _ReplaceTypeAliasAny(ast.NodeTransformer):
    """Remove ``Name: TypeAlias = Any`` statements and replace Name with Any.

    Used when stubtest reports "Type alias for Any" as the stub value and
    MISSING at runtime — the alias is only meaningful for type checking, so
    usages should be inlined as ``Any`` rather than left as undefined names.
    """

    def __init__(self, names: set[str]) -> None:
        self._names = names
        self.changed = False

    def _is_alias_any_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id in self._names
        )

    def visit_Module(self, node: ast.Module) -> ast.Module:
        new_body: list[ast.stmt] = []
        for stmt in node.body:
            if self._is_alias_any_stmt(stmt):
                self.changed = True
            else:
                new_body.append(stmt)
        node.body = new_body
        self.generic_visit(node)
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in self._names:
            self.changed = True
            return ast.copy_location(ast.Name(id="Any", ctx=node.ctx), node)
        return node


class _RemoveNames(ast.NodeTransformer):
    """Remove definitions of specified names from a module or class."""

    def __init__(self, names_to_remove: set[str]) -> None:
        self._top_level = {n for n in names_to_remove if "." not in n}
        self._nested: dict[str, set[str]] = {}
        for n in names_to_remove:
            parts = n.rsplit(".", 1)
            if len(parts) == 2:
                self._nested.setdefault(parts[0], set()).add(parts[1])
        self.changed = False

    def _filter_body(
        self, body: list[ast.stmt], targets: set[str]
    ) -> list[ast.stmt]:
        new_body: list[ast.stmt] = []
        for stmt in body:
            name = self._stmt_name(stmt)
            if name and name in targets:
                self.changed = True
                continue
            new_body.append(stmt)
        if not new_body:
            new_body.append(ast.Expr(value=ast.Constant(value=...)))
        return new_body

    @staticmethod
    def _stmt_name(stmt: ast.stmt) -> str | None:
        if isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            return stmt.name
        if isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.target, ast.Name
        ):
            return stmt.target.id
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                return target.id
        return None

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._filter_body(node.body, self._top_level)
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        targets = self._nested.get(node.name, set())
        if targets:
            node.body = self._filter_body(node.body, targets)
            self.changed = True
        self.generic_visit(node)
        return node


class NotPresentAtRuntimeFixer(ManualFix):
    type: Literal["not_present_at_runtime"] = "not_present_at_runtime"

    _NOT_PRESENT_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"error: (?P<name>[\w.]+) is not present at runtime"
    )
    _TYPE_CHECK_ONLY_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: (?P<name>[\w.]+) is not present at runtime.*Maybe mark it as "@type_check_only"',
        re.DOTALL,
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._NOT_PRESENT_RE.search(e) for e in errors)

    @staticmethod
    def _ensure_type_check_only_import(tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                for alias in node.names:
                    if alias.name == _TYPE_CHECK_ONLY:
                        return
        # Add import
        insert_at = 0
        for i, node in enumerate(tree.body):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_at = i + 1
        tree.body.insert(
            insert_at,
            ast.ImportFrom(
                module="typing",
                names=[ast.alias(name=_TYPE_CHECK_ONLY)],
                level=0,
            ),
        )

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        names_to_remove: set[str] = set()
        names_to_type_check_only: set[str] = set()
        names_to_replace_alias_any: set[str] = set()

        for error in errors:
            m_tco = self._TYPE_CHECK_ONLY_RE.search(error)
            if m_tco:
                full_name = m_tco.group("name")
                local = full_name.rsplit(".", 1)[-1]
                names_to_type_check_only.add(local)
                continue

            m = self._NOT_PRESENT_RE.search(error)
            if m is None:
                continue
            full_name = m.group("name")

            if "Type alias for Any" in error:
                names_to_replace_alias_any.add(full_name.rsplit(".", 1)[-1])
                continue

            parts = full_name.split(".")
            # Always add the bare name for top-level removal.
            # Also add "Class.member" form (last 2 parts) for nested removal.
            # _RemoveNames will only act on what actually exists in the file.
            names_to_remove.add(parts[-1])
            if len(parts) >= 2:
                names_to_remove.add(f"{parts[-2]}.{parts[-1]}")

        # Don't remove things handled by other paths
        names_to_remove -= names_to_type_check_only
        names_to_remove -= names_to_replace_alias_any

        if (
            not names_to_remove
            and not names_to_type_check_only
            and not names_to_replace_alias_any
        ):
            return contents

        tree = ast.parse(contents)
        changed = False

        if names_to_replace_alias_any:
            alias_transformer = _ReplaceTypeAliasAny(
                names_to_replace_alias_any
            )
            tree = alias_transformer.visit(tree)
            if alias_transformer.changed:
                changed = True

        if names_to_type_check_only:
            tco_transformer = _AddTypeCheckOnly(names_to_type_check_only)
            tree = tco_transformer.visit(tree)
            if tco_transformer.changed:
                self._ensure_type_check_only_import(tree)
                changed = True

        if names_to_remove:
            remove_transformer = _RemoveNames(names_to_remove)
            tree = remove_transformer.visit(tree)
            if remove_transformer.changed:
                changed = True

        if not changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
