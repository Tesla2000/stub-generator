import ast
import re
from typing import Literal

from stub_added.transformer.fill_with_llm.manual_fixes._base import ManualFix

# Format 1: per-argument errors
# Argument N of "method" is incompatible with supertype "X";
# supertype defines the argument type as "TYPE"  [override]
_ARG_RE = re.compile(
    r':\d+: error: Argument (?P<n>\d+) of "(?P<method>[^"]+)" '
    r"is incompatible with supertype \"[^\"]+\"; "
    r'supertype defines the argument type as "(?P<expected>[^"]+)"'
)

# Format 2: full-signature errors
# error: Signature of "method" incompatible with supertype "X"  [override]
# note:      Superclass:
# note:          def method(...)
_SIG_RE = re.compile(
    r'error: Signature of "(?P<method>[^"]+)" incompatible with supertype'
)
_DEF_NOTE_RE = re.compile(r"note:\s+def \w+\(")


def _parse_positional_fixes(
    errors: list[str],
) -> dict[tuple[str, int], ast.expr]:
    """Format 1: (method, arg_n) → supertype annotation."""
    fixes: dict[tuple[str, int], ast.expr] = {}
    for error in errors:
        m = _ARG_RE.search(error)
        if not m:
            continue
        key = (m.group("method"), int(m.group("n")))
        if key in fixes:
            continue
        try:
            fixes[key] = ast.parse(m.group("expected"), mode="eval").body
        except SyntaxError:
            pass
    return fixes


def _parse_signature_fixes(
    errors: list[str],
) -> dict[str, list[tuple[str, ast.expr]]]:
    """Format 2: method → ordered [(arg_name, annotation)] from Superclass def note."""
    result: dict[str, list[tuple[str, ast.expr]]] = {}
    seen: set[str] = set()
    i = 0
    while i < len(errors):
        sig_m = _SIG_RE.search(errors[i])
        if not sig_m:
            i += 1
            continue
        method = sig_m.group("method")
        j = i + 1
        while j < len(errors) and not _SIG_RE.search(errors[j]):
            if "Superclass:" in errors[j]:
                if j + 1 < len(errors) and _DEF_NOTE_RE.search(errors[j + 1]):
                    def_line = re.sub(
                        r"^[^:]+:\d+: note:\s+", "", errors[j + 1]
                    ).strip()
                    if method not in seen:
                        seen.add(method)
                        try:
                            tree = ast.parse(f"{def_line}: ...", mode="exec")
                            func = tree.body[0]
                            assert isinstance(func, ast.FunctionDef)
                            all_args = func.args.posonlyargs + func.args.args
                            non_self = (
                                all_args[1:]
                                if all_args
                                and all_args[0].arg in ("self", "cls")
                                else all_args
                            )
                            result[method] = [
                                (arg.arg, arg.annotation)
                                for arg in non_self
                                if arg.annotation
                            ]
                        except SyntaxError:
                            pass
                break
            j += 1
        i += 1
    return result


class _PositionalFixer(ast.NodeTransformer):
    def __init__(self, fixes: dict[tuple[str, int], ast.expr]) -> None:
        self._fixes = fixes

    def _fix(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        all_args = node.args.posonlyargs + node.args.args
        non_self = (
            all_args[1:]
            if all_args and all_args[0].arg in ("self", "cls")
            else all_args
        )
        for (method, n), new_ann in self._fixes.items():
            if node.name != method:
                continue
            idx = n - 1
            if 0 <= idx < len(non_self):
                non_self[idx].annotation = new_ann
        return node

    visit_FunctionDef = _fix
    visit_AsyncFunctionDef = _fix  # type: ignore[assignment]


class _SignatureFixer(ast.NodeTransformer):
    """Reorder and retype non-self args to match the superclass signature."""

    def __init__(
        self, sig_fixes: dict[str, list[tuple[str, ast.expr]]]
    ) -> None:
        self._fixes = sig_fixes

    def _fix(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        if node.name not in self._fixes:
            return node

        superclass_args = self._fixes[
            node.name
        ]  # ordered [(name, annotation)]
        all_args = node.args.posonlyargs + node.args.args
        self_args = (
            all_args[:1]
            if all_args and all_args[0].arg in ("self", "cls")
            else []
        )
        non_self = all_args[len(self_args) :]

        subclass_by_name = {arg.arg: arg for arg in non_self}
        had_default = {
            arg.arg
            for arg in non_self
            if arg in _args_with_defaults(node, len(self_args))
        }

        reordered: list[ast.arg] = []
        for name, super_ann in superclass_args:
            if name not in subclass_by_name:
                continue
            arg = subclass_by_name[name]
            arg.annotation = super_ann
            reordered.append(arg)

        # Any subclass args absent from superclass go at the end unchanged
        super_names = {name for name, _ in superclass_args}
        for arg in non_self:
            if arg.arg not in super_names:
                reordered.append(arg)

        node.args.posonlyargs = []
        node.args.args = self_args + reordered
        # Rebuild defaults: stubs always use `...` so just preserve the count
        default_count = sum(1 for a in reordered if a.arg in had_default)
        node.args.defaults = [ast.Constant(value=...)] * default_count
        return node

    visit_FunctionDef = _fix
    visit_AsyncFunctionDef = _fix  # type: ignore[assignment]


def _args_with_defaults(
    node: ast.FunctionDef, self_count: int
) -> set[ast.arg]:
    """Return the set of positional args that have default values."""
    all_args = node.args.posonlyargs + node.args.args
    non_self = all_args[self_count:]
    n_defaults = len(node.args.defaults)
    return set(non_self[len(non_self) - n_defaults :])


class LspViolationFixer(ManualFix):
    type: Literal["lsp"] = "lsp"

    def __call__(self, contents: str, errors: list[str]) -> str:
        positional = _parse_positional_fixes(errors)
        named = _parse_signature_fixes(errors)

        if not positional and not named:
            return contents

        tree = ast.parse(contents)
        if positional:
            tree = _PositionalFixer(positional).visit(tree)
        if named:
            tree = _SignatureFixer(named).visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
