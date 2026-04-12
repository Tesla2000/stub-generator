import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix


class _RemoveDefaults(ast.NodeTransformer):
    """Remove default values from specified parameters of explicit functions."""

    def __init__(self, removals: dict[str, set[str]]) -> None:
        self._removals = removals  # func_name -> param names
        self.changed = False

    def _process(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.AST:
        params_to_fix = self._removals.get(node.name)
        if not params_to_fix:
            self.generic_visit(node)
            return node

        args = node.args
        # Handle regular args defaults (right-aligned)
        if args.defaults:
            n_no_default = len(args.args) - len(args.defaults)
            new_defaults: list[ast.expr] = []
            new_args: list[ast.arg] = []
            has_default_started = False
            for i, a in enumerate(args.args):
                default_idx = i - n_no_default
                if default_idx >= 0:
                    if a.arg in params_to_fix:
                        self.changed = True
                        # Move this arg before all args with defaults
                        if not has_default_started:
                            new_args.append(a)
                        else:
                            new_args.append(a)
                    else:
                        has_default_started = True
                        new_args.append(a)
                        new_defaults.append(args.defaults[default_idx])
                else:
                    new_args.append(a)
            args.args = new_args
            args.defaults = new_defaults

        # Handle keyword-only defaults
        if args.kw_defaults:
            new_kw_defaults: list[ast.expr | None] = []
            for a, d in zip(args.kwonlyargs, args.kw_defaults):
                if a.arg in params_to_fix and d is not None:
                    self.changed = True
                    new_kw_defaults.append(None)
                else:
                    new_kw_defaults.append(d)
            args.kw_defaults = new_kw_defaults

        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._process(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._process(node)


class _RemoveDataclassDefaults(ast.NodeTransformer):
    """Remove default values from dataclass field annotations.

    Used when stubtest reports a default mismatch for ``__init__`` of a
    dataclass that has no explicit ``def __init__``.
    """

    def __init__(self, class_removals: dict[str, set[str]]) -> None:
        self._class_removals = class_removals  # class_name -> field names
        self.changed = False

    @staticmethod
    def _is_dataclass(node: ast.ClassDef) -> bool:
        for d in node.decorator_list:
            if isinstance(d, ast.Name) and d.id == "dataclass":
                return True
            if isinstance(d, ast.Attribute) and d.attr == "dataclass":
                return True
            if isinstance(d, ast.Call):
                func = d.func
                if isinstance(func, ast.Name) and func.id == "dataclass":
                    return True
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "dataclass"
                ):
                    return True
        return False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.generic_visit(node)
        fields_to_fix = self._class_removals.get(node.name)
        if not fields_to_fix:
            return node
        has_explicit_init = any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "__init__"
            for item in node.body
        )
        if has_explicit_init or not self._is_dataclass(node):
            return node
        for item in node.body:
            if (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id in fields_to_fix
                and item.value is not None
            ):
                item.value = None
                self.changed = True
        return node


class RemoveDefaultFixer(ManualFix):
    type: Literal["remove_default"] = "remove_default"

    _DEFAULT_BUT_NO_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: (?P<func>[\w.]+) is inconsistent, stub parameter "(?P<param>\w+)" has a default value but runtime parameter does not'
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._DEFAULT_BUT_NO_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        func_removals: dict[str, set[str]] = {}
        class_removals: dict[str, set[str]] = {}
        for error in errors:
            m = self._DEFAULT_BUT_NO_RE.search(error)
            if m:
                func_path = m.group("func")
                param = m.group("param")
                func_name = func_path.rsplit(".", 1)[-1]
                func_removals.setdefault(func_name, set()).add(param)
                if func_name == "__init__":
                    class_part = func_path.rsplit(".", 1)[0]
                    class_name = class_part.rsplit(".", 1)[-1]
                    class_removals.setdefault(class_name, set()).add(param)

        if not func_removals and not class_removals:
            return contents

        tree = ast.parse(contents)
        changed = False

        func_transformer = _RemoveDefaults(func_removals)
        tree = func_transformer.visit(tree)
        changed = changed or func_transformer.changed

        if class_removals:
            class_transformer = _RemoveDataclassDefaults(class_removals)
            tree = class_transformer.visit(tree)
            changed = changed or class_transformer.changed

        if not changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
