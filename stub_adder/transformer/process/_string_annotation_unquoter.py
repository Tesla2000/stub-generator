import ast
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class StringAnnotationUnquoter(ProcessBase):
    type: Literal["string_annotation_unquoter"] = "string_annotation_unquoter"

    def process(self, pyi_paths: list[Path]) -> None:
        for path in pyi_paths:
            original = path.read_text()
            fixed = self._unquote(original)
            if fixed != original:
                path.write_text(fixed)

    @staticmethod
    def _unquote(contents: str) -> str:
        tree = ast.parse(contents)
        spans: list[tuple[int, int, int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                spans.extend(_string_spans(node.annotation))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in (
                    node.args.args
                    + node.args.posonlyargs
                    + node.args.kwonlyargs
                    + ([node.args.vararg] if node.args.vararg else [])
                    + ([node.args.kwarg] if node.args.kwarg else [])
                ):
                    if arg.annotation:
                        spans.extend(_string_spans(arg.annotation))
                if node.returns:
                    spans.extend(_string_spans(node.returns))
        if not spans:
            return contents
        lines = contents.splitlines(keepends=True)
        for lineno, col, end_col, value in sorted(spans, reverse=True):
            line = lines[lineno - 1]
            lines[lineno - 1] = line[:col] + value + line[end_col:]
        return "".join(lines)


def _string_spans(node: ast.expr) -> list[tuple[int, int, int, str]]:
    return [
        (n.lineno, n.col_offset, n.end_col_offset, n.value)
        for n in ast.walk(node)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.end_col_offset is not None
    ]
