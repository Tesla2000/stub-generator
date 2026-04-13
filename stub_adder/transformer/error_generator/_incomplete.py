import ast
from collections import defaultdict
from pathlib import Path
from typing import Literal

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase


class Incomplete(ErrorGeneratorBase):
    type: Literal["incomplete"] = "incomplete"

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        errors: defaultdict[Path, list[str]] = defaultdict(list)
        for path in (p.resolve() for p in pyi_paths):
            tree = ast.parse(path.read_text())
            import_lines = {
                node.lineno
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "_typeshed"
            }
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Name)
                    and node.id == "Incomplete"
                    and node.lineno not in import_lines
                ):
                    errors[path].append(
                        f"{path}:{node.lineno}: error: Incomplete type annotation"
                    )
        return dict(errors)
