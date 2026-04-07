import ast
import re
from pathlib import Path
from typing import Literal
from typing import Union

from stub_added._stub_tuple import _StubTuple
from stub_added.transformer._class_finder import find_class_module
from stub_added.transformer.multifile_fixes._base import MultiFileFix

# error: Class cannot subclass "X" (has type "Any")  [misc]
_ANY_BASE_RE = re.compile(
    r':(?P<line>\d+): error: Class cannot subclass "(?P<name>[^"]+)" \(has type "Any"\)'
)


class _BaseRewriter(ast.NodeTransformer):
    """Replace base references and record new imports needed.

    When the defining class has the same name as its base (e.g. ``class Signer(Signer)``),
    we import the parent *module* instead and use ``base.Signer`` to avoid the collision.
    """

    def __init__(self, replacements: dict[int, tuple[str, str]]) -> None:
        # replacements: {lineno: (class_name, new_module)}
        self._replacements = replacements
        # name -> module  (for `from module import name`)
        self.direct_imports: dict[str, str] = {}
        # alias -> parent_module  (for `from parent import alias`)
        self.module_imports: dict[str, str] = {}
        self.changed = False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        if node.lineno not in self._replacements:
            self.generic_visit(node)
            return node
        class_name, new_module = self._replacements[node.lineno]
        collision = node.name == class_name
        new_bases: list[Union[ast.Name, ast.Attribute, ast.expr]] = []
        for base in node.bases:
            base_str = ast.unparse(base)
            if base_str.endswith(f".{class_name}") or base_str == class_name:
                if collision:
                    # Import the module, use `module_alias.ClassName`
                    parts = new_module.rsplit(".", 1)
                    if len(parts) == 2:
                        parent_module, mod_alias = parts
                    else:
                        parent_module, mod_alias = "", parts[0]
                    self.module_imports[mod_alias] = (
                        parent_module or new_module
                    )
                    new_bases.append(
                        ast.Attribute(
                            value=ast.Name(id=mod_alias, ctx=ast.Load()),
                            attr=class_name,
                            ctx=ast.Load(),
                        )
                    )
                else:
                    new_bases.append(ast.Name(id=class_name, ctx=ast.Load()))
                    self.direct_imports[class_name] = new_module
                self.changed = True
            else:
                new_bases.append(base)
        node.bases = new_bases
        self.generic_visit(node)
        return node


def _ensure_direct_import(
    tree: ast.Module, name: str, module: str
) -> ast.Module:
    """Add ``from <module> import <name>``, replacing any existing import of <name>."""
    new_body: list[ast.stmt] = []
    insert_at = 0
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.ImportFrom):
            node.names = [
                a for a in node.names if a.name != name and a.asname != name
            ]
            if not node.names:
                insert_at = i
                continue
            insert_at = i + 1
        elif isinstance(node, ast.Import):
            insert_at = i + 1
        new_body.append(node)

    new_import = ast.ImportFrom(
        module=module,
        names=[ast.alias(name=name)],
        level=0,
    )
    new_body.insert(insert_at, new_import)
    tree.body = new_body
    return tree


def _ensure_module_import(
    tree: ast.Module, alias: str, parent_module: str
) -> ast.Module:
    """Add ``from <parent_module> import <alias>``, replacing any conflicting import."""
    new_body: list[ast.stmt] = []
    insert_at = 0
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.ImportFrom):
            node.names = [
                a for a in node.names if a.asname != alias and a.name != alias
            ]
            if not node.names:
                insert_at = i
                continue
            insert_at = i + 1
        elif isinstance(node, ast.Import):
            insert_at = i + 1
        new_body.append(node)

    new_import = ast.ImportFrom(
        module=parent_module,
        names=[ast.alias(name=alias)],
        level=0,
    )
    new_body.insert(insert_at, new_import)
    tree.body = new_body
    return tree


class AnyBaseFixer(MultiFileFix):
    type: Literal["any_base"] = "any_base"

    def __call__(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None:
        for pyi, errors in errors_by_file.items():
            self._fix_file(pyi, errors, stubs_dir)

    def _fix_file(self, pyi: Path, errors: list[str], stubs_dir: Path) -> None:
        # {lineno: (class_name, new_module)}
        replacements: dict[int, tuple[str, str]] = {}
        source_text = pyi.read_text()
        source_tree = ast.parse(source_text)

        for error in errors:
            m = _ANY_BASE_RE.search(error)
            if not m:
                continue
            lineno = int(m.group("line"))
            class_name = m.group("name")
            module = find_class_module(
                class_name, source_tree, stubs_dir, lineno=lineno
            )
            if module is None:
                continue
            replacements[lineno] = (class_name, module)

        if not replacements:
            return

        tree = ast.parse(source_text)
        rewriter = _BaseRewriter(replacements)
        tree = rewriter.visit(tree)
        if not rewriter.changed:
            return

        for name, module in rewriter.direct_imports.items():
            tree = _ensure_direct_import(tree, name, module)
        for alias, parent in rewriter.module_imports.items():
            tree = _ensure_module_import(tree, alias, parent)

        ast.fix_missing_locations(tree)
        pyi.write_text(ast.unparse(tree))
