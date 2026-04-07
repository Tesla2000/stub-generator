import ast
import builtins
import importlib
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import ClassVar
from typing import Literal

import autoimport
import mypy
from stub_added.transformer._class_finder import find_class_module
from stub_added.transformer._class_finder import find_name_in_supertype_stubs
from stub_added.transformer.file_fix._base import ManualFix


class ImportFixer(ManualFix):
    type: Literal["import"] = "import"
    _BUILTIN_NAMES: ClassVar[frozenset[str]] = frozenset(vars(builtins))
    _NAME_DEFINED_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: Name "(?P<name>[^"]+)" is not defined'
    )
    _SUPERTYPE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'(?:incompatible with supertype|in supertype) "(?P<supertype>[^"]+)"'
    )

    @staticmethod
    @cache
    def _typeshed_names() -> frozenset[str]:
        stub = (
            Path(mypy.__file__).parent
            / "typeshed/stdlib/_typeshed/__init__.pyi"
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

    @staticmethod
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

    @staticmethod
    def _supertype_candidate_modules(errors: list[str]) -> list[str]:
        modules: list[str] = []
        seen: set[str] = set()
        for error in errors:
            m = ImportFixer._SUPERTYPE_RE.search(error)
            if not m:
                continue
            parts = m.group("supertype").split(".")
            for i in range(len(parts) - 1, 0, -1):
                module = ".".join(parts[:i])
                if module not in seen:
                    seen.add(module)
                    modules.append(module)
        return modules

    @staticmethod
    def _add_missing_imports(
        code: str, undefined: set[str], candidate_modules: list[str]
    ) -> str:
        if not undefined:
            return code
        typeshed = ImportFixer._typeshed_names()
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

    @staticmethod
    def _locally_defined_names(tree: ast.Module) -> set[str]:
        """Return names defined at module level (classes, functions, assignments)."""
        names: set[str] = set()
        for node in tree.body:
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                names.add(node.name)
            elif isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name
            ):
                names.add(node.target.id)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
        return names

    @staticmethod
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

    @staticmethod
    def resolve_missing_imports(code: str, errors: list[str]) -> str:
        """Add imports for names flagged as undefined via [name-defined] errors,
        using autoimport, _typeshed, and supertype module search as fallbacks.
        """
        code = autoimport.fix_code(code)
        tree = ast.parse(code)
        undefined = (
            {
                m.group("name")
                for error in errors
                if (m := ImportFixer._NAME_DEFINED_RE.search(error))
            }
            - ImportFixer._imported_names(tree)
            - ImportFixer._BUILTIN_NAMES
        )
        return ImportFixer._add_missing_imports(
            code, undefined, ImportFixer._supertype_candidate_modules(errors)
        )

    @staticmethod
    def resolve_annotation_imports(
        code: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        """Add imports for all names used in annotations that are not yet imported.
        Used after AST fixes that introduce new type names without corresponding imports.
        Raises RuntimeError if any annotation name cannot be resolved.
        """
        code = autoimport.fix_code(code)
        tree = ast.parse(code)
        undefined = (
            ImportFixer._annotation_names(tree)
            - ImportFixer._imported_names(tree)
            - ImportFixer._BUILTIN_NAMES
        )
        code = ImportFixer._add_missing_imports(
            code, undefined, ImportFixer._supertype_candidate_modules(errors)
        )

        # Fallback: follow import chain in stubs to locate still-undefined names
        if stubs_dir is not None:
            tree = ast.parse(code)
            still_undefined = (
                ImportFixer._annotation_names(tree)
                - ImportFixer._imported_names(tree)
                - ImportFixer._BUILTIN_NAMES
            )
            supertype_modules = ImportFixer._supertype_candidate_modules(
                errors
            )
            for name in still_undefined:
                # First try: follow the import chain from the current file
                module = find_class_module(name, tree, stubs_dir)
                # Second try: look at how the name appears in supertype stubs
                if module is None:
                    module = find_name_in_supertype_stubs(
                        name, supertype_modules, stubs_dir
                    )
                if module is not None:
                    code = f"from {module} import {name}\n" + code

        # Final check — raise if anything remains unresolved
        tree = ast.parse(code)
        unresolved = (
            ImportFixer._annotation_names(tree)
            - ImportFixer._imported_names(tree)
            - ImportFixer._BUILTIN_NAMES
            - ImportFixer._locally_defined_names(tree)
        )
        if unresolved:
            raise RuntimeError(
                f"Could not resolve annotation imports: {unresolved}"
            )
        return code

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._NAME_DEFINED_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._NAME_DEFINED_RE.search(e) for e in errors):
            return contents
        return self.resolve_missing_imports(contents, errors)
