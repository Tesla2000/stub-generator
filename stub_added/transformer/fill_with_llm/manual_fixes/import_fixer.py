import ast
import builtins
import importlib
import re
from functools import cache
from pathlib import Path
from typing import Literal

import autoimport
import mypy
from stub_added.transformer.fill_with_llm.manual_fixes._base import ManualFix

_BUILTIN_NAMES: frozenset[str] = frozenset(vars(builtins))

_NAME_DEFINED_RE = re.compile(r'error: Name "(?P<name>[^"]+)" is not defined')
_SUPERTYPE_RE = re.compile(
    r'incompatible with supertype "(?P<supertype>[^"]+)"'
)


@cache
def _typeshed_names() -> frozenset[str]:
    stub = (
        Path(mypy.__file__).parent / "typeshed/stdlib/_typeshed/__init__.pyi"
    )
    tree = ast.parse(stub.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return frozenset(names)


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _supertype_candidate_modules(errors: list[str]) -> list[str]:
    modules: list[str] = []
    seen: set[str] = set()
    for error in errors:
        m = _SUPERTYPE_RE.search(error)
        if not m:
            continue
        parts = m.group("supertype").split(".")
        for i in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:i])
            if module not in seen:
                seen.add(module)
                modules.append(module)
    return modules


def _add_missing_imports(
    code: str, undefined: set[str], candidate_modules: list[str]
) -> str:
    if not undefined:
        return code
    typeshed = _typeshed_names()
    extra: list[str] = []
    for name in sorted(undefined):
        if name in typeshed:
            extra.append(f"from _typeshed import {name}")
            continue
        for module_name in candidate_modules:
            try:
                mod = importlib.import_module(module_name)
                if hasattr(mod, name):  # ignore
                    extra.append(f"from {module_name} import {name}")
                    break
            except ImportError:
                continue
    if not extra:
        return code
    return "\n".join(extra) + "\n" + code


def resolve_missing_imports(code: str, errors: list[str]) -> str:
    """Add imports for names flagged as undefined via [name-defined] errors,
    using autoimport, _typeshed, and supertype module search as fallbacks."""
    code = autoimport.fix_code(code)
    tree = ast.parse(code)
    undefined = (
        {
            m.group("name")
            for error in errors
            if (m := _NAME_DEFINED_RE.search(error))
        }
        - _imported_names(tree)
        - _BUILTIN_NAMES
    )
    return _add_missing_imports(
        code, undefined, _supertype_candidate_modules(errors)
    )


def resolve_annotation_imports(code: str, errors: list[str]) -> str:
    """Add imports for all names used in annotations that are not yet imported.
    Used after AST fixes that introduce new type names without corresponding imports.
    """
    code = autoimport.fix_code(code)
    tree = ast.parse(code)
    undefined = (
        _annotation_names(tree) - _imported_names(tree) - _BUILTIN_NAMES
    )
    return _add_missing_imports(
        code, undefined, _supertype_candidate_modules(errors)
    )


def _annotation_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_arg_nodes = (
                node.args.args
                + node.args.posonlyargs
                + node.args.kwonlyargs
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            )
            for arg in all_arg_nodes:
                if arg.annotation:
                    for n in ast.walk(arg.annotation):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
            if node.returns:
                for n in ast.walk(node.returns):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.AnnAssign):
            for n in ast.walk(node.annotation):
                if isinstance(n, ast.Name):
                    names.add(n.id)
    return names


class ImportFixer(ManualFix):
    type: Literal["import"] = "import"

    def __call__(self, contents: str, errors: list[str]) -> str:
        if not any(_NAME_DEFINED_RE.search(e) for e in errors):
            return contents
        return resolve_missing_imports(contents, errors)
