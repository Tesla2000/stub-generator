import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix


class _RemoveClassmethod(ast.NodeTransformer):
    """Remove @classmethod decorator and rename cls -> self."""

    def __init__(self, func_names: set[str]) -> None:
        self._names = func_names
        self.changed = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name not in self._names:
            self.generic_visit(node)
            return node

        node.decorator_list = [
            d
            for d in node.decorator_list
            if not (isinstance(d, ast.Name) and d.id == "classmethod")
        ]
        self.changed = True
        self.generic_visit(node)
        return node


class ClassmethodFixer(ManualFix):
    type: Literal["classmethod_fixer"] = "classmethod_fixer"

    _CLASSMETHOD_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"error: (?P<name>[\w.]+) is inconsistent, stub is a classmethod but runtime is not"
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._CLASSMETHOD_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        func_names: set[str] = set()
        for error in errors:
            m = self._CLASSMETHOD_RE.search(error)
            if m:
                func_names.add(m.group("name").rsplit(".", 1)[-1])

        if not func_names:
            return contents

        tree = ast.parse(contents)
        transformer = _RemoveClassmethod(func_names)
        tree = transformer.visit(tree)
        if not transformer.changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
