import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Literal

from stub_adder.transformer.file_fix._base import ManualFix


class _FuncToAsync(ast.NodeTransformer):
    """Convert specific FunctionDef nodes to AsyncFunctionDef."""

    def __init__(self, func_names: set[str]) -> None:
        self._names = func_names
        self.changed = False

    def _convert(self, node: ast.FunctionDef) -> ast.AST:
        if node.name not in self._names:
            return node
        self.changed = True
        new_node = ast.AsyncFunctionDef(
            name=node.name,
            args=node.args,
            body=node.body,
            decorator_list=node.decorator_list,
            returns=node.returns,
            type_comment=node.type_comment,
            type_params=node.type_params,
            lineno=node.lineno,
            col_offset=node.col_offset,
        )
        return new_node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._convert(node)


class AsyncDefStubFixer(ManualFix):
    type: Literal["async_def_stub"] = "async_def_stub"

    _ASYNC_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: (?P<name>[\w.]+) is an "async def" function at runtime, but not in the stub'
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._ASYNC_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        func_names: set[str] = set()
        for error in errors:
            m = self._ASYNC_RE.search(error)
            if m:
                # Get just the function name (last component)
                func_names.add(m.group("name").rsplit(".", 1)[-1])

        if not func_names:
            return contents

        tree = ast.parse(contents)
        transformer = _FuncToAsync(func_names)
        tree = transformer.visit(tree)
        if not transformer.changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
