import ast
import re
from pathlib import Path
from typing import Literal

from stub_added.transformer.file_fix._base import ManualFix

_ABSTRACT_RE = re.compile(
    r'error: Class \S+ has abstract attributes? "[^"]+"  \[misc\]'
)
_CLASS_NAME_RE = re.compile(r"error: Class (\S+) has abstract attributes?")


def _local_class_name(full_name: str) -> str:
    """Extract the unqualified class name from a fully-qualified name."""
    return full_name.rsplit(".", 1)[-1]


class _AddAbcMetaTransformer(ast.NodeTransformer):
    def __init__(self, class_names: set[str]) -> None:
        self._names = class_names

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        self.generic_visit(node)
        if node.name not in self._names:
            return node
        # Already has abc.ABCMeta or ABCMeta keyword
        for kw in node.keywords:
            if kw.arg == "metaclass":
                return node
        node.keywords.append(
            ast.keyword(
                arg="metaclass",
                value=ast.Attribute(
                    value=ast.Name(id="abc", ctx=ast.Load()),
                    attr="ABCMeta",
                    ctx=ast.Load(),
                ),
            )
        )
        return node


class AbstractClassFixer(ManualFix):
    type: Literal["abstract_class"] = "abstract_class"

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        class_names = {
            _local_class_name(m.group(1))
            for e in errors
            if (m := _CLASS_NAME_RE.search(e))
        }
        if not class_names:
            return contents

        tree = ast.parse(contents)
        new_tree = _AddAbcMetaTransformer(class_names).visit(tree)
        ast.fix_missing_locations(new_tree)
        result = ast.unparse(new_tree)

        # Ensure abc is imported
        if "import abc" not in result and "abc.ABCMeta" in result:
            result = "import abc\n" + result

        return result
