import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix


class _UpdateDefaults(ast.NodeTransformer):
    """Update default values for specific parameters to match runtime."""

    def __init__(self, updates: dict[str, dict[str, ast.expr]]) -> None:
        # func_name -> {param_name -> new_default_expr}
        self._updates = updates
        self.changed = False

    def _process(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.AST:
        param_updates = self._updates.get(node.name)
        if not param_updates:
            self.generic_visit(node)
            return node

        args = node.args
        n_no_default = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            default_idx = i - n_no_default
            if default_idx >= 0 and arg.arg in param_updates:
                args.defaults[default_idx] = param_updates[arg.arg]
                self.changed = True

        for i, arg in enumerate(args.kwonlyargs):
            if arg.arg in param_updates and i < len(args.kw_defaults):
                args.kw_defaults[i] = param_updates[arg.arg]
                self.changed = True

        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._process(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._process(node)


class DefaultValueFixer(ManualFix):
    type: Literal["default_value"] = "default_value"

    _DEFAULT_MISMATCH_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: (?P<func>[\w.]+) is inconsistent, runtime parameter "(?P<param>\w+)" '
        r"has a default value of (?P<value>.+?), which is different from stub parameter default"
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._DEFAULT_MISMATCH_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        updates: dict[str, dict[str, ast.expr]] = {}
        for error in errors:
            m = self._DEFAULT_MISMATCH_RE.search(error)
            if m is None:
                continue
            func_name = m.group("func").rsplit(".", 1)[-1]
            param = m.group("param")
            value_str = m.group("value").strip()
            try:
                new_default: ast.expr = ast.parse(value_str, mode="eval").body
            except SyntaxError:
                continue
            updates.setdefault(func_name, {})[param] = new_default

        if not updates:
            return contents

        tree = ast.parse(contents)
        transformer = _UpdateDefaults(updates)
        tree = transformer.visit(tree)
        if not transformer.changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
