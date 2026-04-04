import ast

import autoflake  # type: ignore[import-untyped]
import autoimport
import black
import isort


class _AnnotationFixer(ast.NodeTransformer):
    """Replace bare *args/**kwargs and `object` annotations with `Any`."""

    def _any(self) -> ast.Name:
        return ast.Name(id="Any", ctx=ast.Load())

    def _is_object(self, node: ast.expr | None) -> bool:
        return isinstance(node, ast.Name) and node.id == "object"

    def _fix_args_annotation(self, arg: ast.arg) -> ast.arg:
        if self._is_object(arg.annotation):
            arg.annotation = self._any()
        return arg

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        if node.args.vararg and node.args.vararg.annotation is None:
            node.args.vararg.annotation = self._any()
        if node.args.kwarg and node.args.kwarg.annotation is None:
            node.args.kwarg.annotation = self._any()
        for arg in (
            node.args.args + node.args.posonlyargs + node.args.kwonlyargs
        ):
            self._fix_args_annotation(arg)
        if self._is_object(node.returns):
            node.returns = self._any()
        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign:
        if self._is_object(node.annotation):
            node.annotation = self._any()
        return node


def _fix_annotations(contents: str) -> str:
    tree = ast.parse(contents)
    tree = _AnnotationFixer().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def postprocess_stub(contents: str) -> str:
    contents = autoimport.fix_code(contents)
    contents = _fix_annotations(contents)
    contents = autoflake.fix_code(
        contents,
        remove_all_unused_imports=True,
        remove_unused_variables=False,
    )
    contents = isort.code(contents)
    contents = black.format_str(contents, mode=black.Mode(is_pyi=True))
    return contents
