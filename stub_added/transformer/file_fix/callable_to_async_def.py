import ast
import re
from pathlib import Path
from typing import Literal

from stub_added.transformer.file_fix._base import ManualFix

# error: Incompatible types in assignment (expression has type
#        "Callable[[...], Coroutine[Any, Any, X]]", base class "ClassName"
#        defined the type as "Callable[[...], X]")  [assignment]
_CALLABLE_ASSIGN_RE = re.compile(
    r":(?P<line>\d+): error: Incompatible types in assignment "
    r'\(expression has type "(?P<expr>[^"]*Coroutine[^"]*)"'
)

# Extract `[[p1, p2, ...], Coroutine[Any, Any, RetType]]` from a Callable string
_CALLABLE_PARSE_RE = re.compile(
    r"Callable\[(?P<params>\[.*?\]), Coroutine\[Any, Any, (?P<ret>.+?)\]\]$"
)


def _find_method(
    tree: ast.Module, class_name: str, method_name: str
) -> ast.FunctionDef | None:
    """Find a method definition in a named class."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                ):
                    return item  # type: ignore[return-value]
    return None


def _parse_callable_params(
    expr: str,
) -> tuple[list[ast.expr], ast.expr] | None:
    """Parse a Callable[[...], Coroutine[Any, Any, Ret]] into (param_annotations, return_annotation)."""
    m = _CALLABLE_PARSE_RE.search(expr)
    if not m:
        return None
    params_str = m.group(
        "params"
    )  # e.g. "[Request, str, str, Mapping[str, str]]"
    ret_str = m.group("ret")  # e.g. "None"
    # Strip outer brackets and split by top-level commas
    inner = params_str[1:-1].strip()
    if not inner:
        param_types: list[str] = []
    else:
        param_types = _split_top_level(inner)
    try:
        param_anns = [
            ast.parse(t.strip(), mode="eval").body for t in param_types
        ]
        ret_ann = ast.parse(ret_str.strip(), mode="eval").body
    except SyntaxError:
        return None
    return param_anns, ret_ann  # type: ignore[return-value]


def _split_top_level(s: str) -> list[str]:
    """Split `s` by commas that are not inside brackets."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _build_async_def_from_expr(
    method_name: str, expr: str, lineno: int, col_offset: int
) -> ast.AsyncFunctionDef | None:
    """Build an async def node from a Callable expression in the error message."""
    parsed = _parse_callable_params(expr)
    if parsed is None:
        return None
    param_anns, ret_ann = parsed
    # First param type is `self` (no annotation), rest get arg names arg0, arg1, ...
    args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg="self")]
        + [
            ast.arg(arg=f"arg{i}", annotation=ann)
            for i, ann in enumerate(param_anns)
        ],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )
    return ast.AsyncFunctionDef(
        name=method_name,
        args=args,
        body=[ast.Expr(value=ast.Constant(value=...))],
        decorator_list=[],
        returns=ret_ann,
        type_comment=None,
        type_params=[],
        lineno=lineno,
    )


class _AssignmentToAsyncDef(ast.NodeTransformer):
    """Replace `method = Class.method` with `async def method(...)` in classes at given lines."""

    def __init__(self, tree: ast.Module, replacements: dict[int, str]) -> None:
        self._tree = tree
        self._replacements = replacements  # lineno -> callable expr string
        self.changed = False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        new_body: list[ast.stmt] = []
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and stmt.lineno in self._replacements
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                method_name = stmt.targets[0].id
                async_node: ast.AsyncFunctionDef | None = None
                # Try to find the method in the same file first
                if isinstance(stmt.value, ast.Attribute):
                    ref_class = ast.unparse(stmt.value.value)
                    source = _find_method(self._tree, ref_class, method_name)
                    if source is not None:
                        async_node = ast.AsyncFunctionDef(
                            name=method_name,
                            args=source.args,
                            body=[ast.Expr(value=ast.Constant(value=...))],
                            decorator_list=[],
                            returns=ast.Constant(value=None),
                            type_comment=None,
                            type_params=[],
                            lineno=stmt.lineno,
                            col_offset=stmt.col_offset,
                        )
                # Fallback: build from the Callable type in the error message
                if async_node is None:
                    expr = self._replacements[stmt.lineno]
                    async_node = _build_async_def_from_expr(
                        method_name, expr, stmt.lineno, stmt.col_offset
                    )
                if async_node is not None:
                    new_body.append(async_node)
                    self.changed = True
                    continue
            new_body.append(stmt)
        node.body = new_body
        self.generic_visit(node)
        return node


class CallableToAsyncDef(ManualFix):
    type: Literal["callable_to_async_def"] = "callable_to_async_def"

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        replacements: dict[int, str] = {}
        for error in errors:
            m = _CALLABLE_ASSIGN_RE.search(error)
            if m:
                replacements[int(m.group("line"))] = m.group("expr")

        if not replacements:
            return contents

        tree = ast.parse(contents)
        transformer = _AssignmentToAsyncDef(tree, replacements)
        tree = transformer.visit(tree)
        if not transformer.changed:
            return contents

        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
