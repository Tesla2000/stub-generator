"""Resolve the true stub module that defines a class, by following import chains."""

import ast
from pathlib import Path


def _stub_path(module: str, stubs_dir: Path) -> Path | None:
    """Return the .pyi path for a dotted module name, or None if not found."""
    parts = module.split(".")
    pkg = stubs_dir.joinpath(*parts) / "__init__.pyi"
    if pkg.exists():
        return pkg
    mod = stubs_dir.joinpath(*parts[:-1]) / f"{parts[-1]}.pyi"
    if mod.exists():
        return mod
    return None


def _imported_from(class_name: str, tree: ast.Module) -> str | None:
    """Return the module `class_name` is imported from in this AST, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == class_name or alias.asname == class_name:
                    return node.module
    return None


def _full_module_for_alias(alias: str, tree: ast.Module) -> str | None:
    """Return the full dotted module path for a name imported as a submodule.

    For ``from pkg import crypt``, returns ``"pkg.crypt"`` when asked for ``"crypt"``.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                if a.name == alias or a.asname == alias:
                    return f"{node.module}.{a.name}"
    return None


def _source_module(
    class_name: str, source_tree: ast.Module, lineno: int | None
) -> str | None:
    """Return the module that `class_name` comes from in `source_tree`.

    When `lineno` is given, also checks attribute-access bases (e.g. ``crypt.Signer``)
    at the ClassDef on that line.
    """
    if lineno is not None:
        for node in ast.walk(source_tree):
            if isinstance(node, ast.ClassDef) and node.lineno == lineno:
                for base in node.bases:
                    base_str = ast.unparse(base)
                    if base_str.endswith(f".{class_name}"):
                        mod_expr = base_str[: -len(f".{class_name}")]
                        first_alias = mod_expr.split(".")[0]
                        parent = _full_module_for_alias(
                            first_alias, source_tree
                        )
                        if parent is None:
                            parent = _imported_from(first_alias, source_tree)
                        if parent is None:
                            return None
                        rest = (
                            mod_expr.split(".", 1)[1]
                            if "." in mod_expr
                            else ""
                        )
                        return f"{parent}.{rest}" if rest else parent
                    if base_str == class_name:
                        return _imported_from(class_name, source_tree)

    return _imported_from(class_name, source_tree)


def _is_real_class(class_name: str, text: str) -> bool:
    """Return True if `text` defines `class <name>` that does NOT inherit itself."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            base_names = {ast.unparse(b) for b in node.bases}
            if class_name not in base_names and not any(
                b.endswith(f".{class_name}") for b in base_names
            ):
                return True
    return False


def _scan_package_dir(
    class_name: str, module: str, stubs_dir: Path
) -> str | None:
    """Scan only the package directory of `module` for a stub defining `class_name`.

    Used as a last resort when the module's __init__.pyi exposes the name as Any
    (no import chain to follow), but the real definition is in a sibling submodule.
    """
    parts = module.split(".")
    pkg_dir = stubs_dir.joinpath(*parts)
    if not pkg_dir.is_dir():
        return None
    for pyi in sorted(pkg_dir.rglob("*.pyi")):
        if pyi.name == "__init__.pyi":
            continue
        try:
            text = pyi.read_text()
        except OSError:
            continue
        if _is_real_class(class_name, text):
            rel = pyi.relative_to(stubs_dir).with_suffix("")
            return ".".join(rel.parts)
    return None


def find_class_module(
    class_name: str,
    source_tree: ast.Module,
    stubs_dir: Path,
    lineno: int | None = None,
    _depth: int = 0,
) -> str | None:
    """Return the dotted module path whose stub truly defines `class_name`.

    Starts from the import (or base-class attribute expression) in `source_tree`,
    then recursively follows re-export chains until the real definition is found.
    As a last resort, scans the resolved module's own package directory.
    Returns None if the class cannot be located.
    """
    if _depth > 10:
        return None

    module = _source_module(class_name, source_tree, lineno)
    if module is None:
        return None

    stub = _stub_path(module, stubs_dir)
    if stub is None:
        return None

    try:
        text = stub.read_text()
    except OSError:
        return None

    if _is_real_class(class_name, text):
        return module

    # Follow import chain recursively
    inner_tree = ast.parse(text)
    result = find_class_module(
        class_name, inner_tree, stubs_dir, lineno=None, _depth=_depth + 1
    )
    if result is not None:
        return result

    # Last resort: scan the package directory (e.g. when __init__.pyi has `Name: Any`)
    return _scan_package_dir(class_name, module, stubs_dir)


def find_class_by_annotation_attr(
    class_name: str, tree: ast.Module, stubs_dir: Path
) -> str | None:
    """Find the module for `class_name` by scanning attribute expressions in
    the annotations of `tree` itself (e.g. ``google.auth.crypt.Signer`` → ``google.auth.crypt.base``).

    Used when `class_name` was introduced as a bare name by a fixer but the
    original file references it only through a dotted attribute in some other
    annotation, not through a plain ``from ... import`` statement.
    """
    for node in ast.walk(tree):
        ann: ast.expr | None = None
        if isinstance(node, ast.arg):
            ann = node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ann = node.returns
        elif isinstance(node, ast.AnnAssign):
            ann = node.annotation
        if ann is None:
            continue
        for sub in ast.walk(ann):
            if not isinstance(sub, ast.Attribute) or sub.attr != class_name:
                continue
            mod_expr = ast.unparse(sub.value)
            stub = _stub_path(mod_expr, stubs_dir)
            if stub is None:
                continue
            try:
                text = stub.read_text()
            except OSError:
                continue
            if _is_real_class(class_name, text):
                return mod_expr
            inner = ast.parse(text)
            result = find_class_module(class_name, inner, stubs_dir)
            if result is not None:
                return result
            result = _scan_package_dir(class_name, mod_expr, stubs_dir)
            if result is not None:
                return result
    return None


def find_name_in_supertype_stubs(
    name: str,
    supertype_modules: list[str],
    stubs_dir: Path,
) -> str | None:
    """Find the module that truly defines `name` by inspecting supertype stub annotations.

    Used when `name` was introduced as a bare annotation by a fixer (e.g. LspViolationFixer)
    but is not imported in the source file. Looks at how the name appears in annotations
    within the supertype stubs (e.g. as ``_credentials.Signing``) and follows that chain.
    """
    for module in supertype_modules:
        stub = _stub_path(module, stubs_dir)
        if stub is None:
            continue
        try:
            text = stub.read_text()
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue

        # Fast path: the supertype stub directly defines the class
        if _is_real_class(name, text):
            return module

        # Search all annotations for patterns like `alias.name` or bare `name`
        for node in ast.walk(tree):
            ann: ast.expr | None = None
            if isinstance(node, ast.arg):
                ann = node.annotation
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ann = node.returns
            elif isinstance(node, ast.AnnAssign):
                ann = node.annotation
            if ann is None:
                continue
            ann_str = ast.unparse(ann).strip("'\"")
            if ann_str.endswith(f".{name}"):
                # e.g. `_credentials.Signing` — resolve `_credentials`
                mod_expr = ann_str[: -len(f".{name}")]
                first_alias = mod_expr.split(".")[0]
                full_mod = _full_module_for_alias(first_alias, tree)
                if full_mod is None:
                    full_mod = _imported_from(first_alias, tree)
                if full_mod is None:
                    continue
                rest = mod_expr.split(".", 1)[1] if "." in mod_expr else ""
                candidate_module = f"{full_mod}.{rest}" if rest else full_mod
                candidate_stub = _stub_path(candidate_module, stubs_dir)
                if candidate_stub and _is_real_class(
                    name, candidate_stub.read_text()
                ):
                    return candidate_module
            elif ann_str == name:
                # Bare name — find via import in the supertype stub
                mod = _imported_from(name, tree)
                if mod:
                    candidate_stub = _stub_path(mod, stubs_dir)
                    if candidate_stub and _is_real_class(
                        name, candidate_stub.read_text()
                    ):
                        return mod

    return None
