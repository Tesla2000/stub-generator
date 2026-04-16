import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Literal

from stub_adder.transformer.file_fix._base import ManualFix


class _RemoveParams(ast.NodeTransformer):
    """Remove named parameters from function definitions."""

    def __init__(self, removals: dict[str, set[str]]) -> None:
        # func_name -> set of param names to remove
        self._removals = removals
        self.changed = False

    def _process(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.AST:
        params_to_remove = self._removals.get(node.name)
        if not params_to_remove:
            self.generic_visit(node)
            return node

        args = node.args
        for attr in ("args", "posonlyargs", "kwonlyargs"):
            arg_list: list[ast.arg] = getattr(args, attr)  # ignore
            new_list = [a for a in arg_list if a.arg not in params_to_remove]
            if len(new_list) != len(arg_list):
                self.changed = True
                setattr(args, attr, new_list)
                # Also remove corresponding defaults
                if attr == "args":
                    n_no_default = len(arg_list) - len(args.defaults)
                    new_defaults = []
                    for i, a in enumerate(arg_list):
                        default_idx = i - n_no_default
                        if a.arg not in params_to_remove and default_idx >= 0:
                            new_defaults.append(args.defaults[default_idx])
                    args.defaults = new_defaults
                elif attr == "kwonlyargs":
                    new_kw_defaults = []
                    for a, d in zip(arg_list, args.kw_defaults):
                        if a.arg not in params_to_remove:
                            new_kw_defaults.append(d)
                    args.kw_defaults = new_kw_defaults

        if args.vararg and args.vararg.arg in params_to_remove:
            args.vararg = None
            self.changed = True
        if args.kwarg and args.kwarg.arg in params_to_remove:
            args.kwarg = None
            self.changed = True

        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._process(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._process(node)


class RemoveExtraParamFixer(ManualFix):
    type: Literal["remove_extra_param"] = "remove_extra_param"

    # Covers regular params, *args, and **kwargs:
    #   runtime does not have parameter "x"
    #   runtime does not have *args parameter "args"
    #   runtime does not have **kwargs parameter "kwargs"
    _EXTRA_PARAM_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"error: (?P<func>[\w.]+) is inconsistent, runtime does not have "
        r'(?:\*{0,2}\w+ )?parameter "(?P<param>\w+)"'
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._EXTRA_PARAM_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        removals: dict[str, set[str]] = {}
        for error in errors:
            m = self._EXTRA_PARAM_RE.search(error)
            if m:
                func_name = m.group("func").rsplit(".", 1)[-1]
                removals.setdefault(func_name, set()).add(m.group("param"))

        if not removals:
            return contents

        tree = ast.parse(contents)
        transformer = _RemoveParams(removals)
        tree = transformer.visit(tree)
        if not transformer.changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
