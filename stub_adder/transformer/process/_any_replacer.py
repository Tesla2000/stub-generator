import ast
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class AnyReplacer(ProcessBase):
    type: Literal["any_replacer"] = "any_replacer"

    def process(self, pyi_paths: list[Path]) -> None:
        for path in pyi_paths:
            original = path.read_text()
            fixed = self._replace(original)
            if fixed != original:
                path.write_text(fixed)

    @staticmethod
    def _replace(contents: str) -> str:
        tree = ast.parse(contents)
        spans: list[tuple[int, int, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                spans.extend(_any_spans(node.annotation))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for arg in (
                    node.args.args
                    + node.args.posonlyargs
                    + node.args.kwonlyargs
                    + ([node.args.vararg] if node.args.vararg else [])
                    + ([node.args.kwarg] if node.args.kwarg else [])
                ):
                    if arg.annotation:
                        spans.extend(_any_spans(arg.annotation))
                if node.returns:
                    spans.extend(_any_spans(node.returns))
        if not spans:
            return contents
        lines = contents.splitlines(keepends=True)
        for lineno, col, end_col in sorted(spans, reverse=True):
            line = lines[lineno - 1]
            lines[lineno - 1] = line[:col] + "object" + line[end_col:]
        return "".join(lines)


def _any_spans(node: ast.expr) -> list[tuple[int, int, int]]:
    return [
        (n.lineno, n.col_offset, n.end_col_offset)
        for n in ast.walk(node)
        if isinstance(n, ast.Name)
        and n.id == "Any"
        and n.end_col_offset is not None
    ]
