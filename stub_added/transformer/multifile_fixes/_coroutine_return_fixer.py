import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_added._stub_tuple import _StubTuple
from stub_added.transformer.error_generator import Mypy
from stub_added.transformer.multifile_fixes._base import MultiFileFix


class _ReturnWidener(ast.NodeTransformer):
    """Widen return types of specific methods inside a named class."""

    def __init__(
        self, class_name: str, method_fixes: dict[str, ast.expr]
    ) -> None:
        self._class_name = class_name
        self._method_fixes = method_fixes
        self.changed = False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        if node.name == self._class_name:
            self.generic_visit(node)
        return node

    def _widen(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if node.name not in self._method_fixes:
            return node
        extra = self._method_fixes[node.name]
        existing = node.returns
        if existing is None:
            node.returns = extra
        else:
            node.returns = ast.BinOp(
                left=existing, op=ast.BitOr(), right=extra
            )
        self.changed = True
        return node

    visit_FunctionDef = _widen
    visit_AsyncFunctionDef = _widen  # type: ignore[assignment]


class CoroutineReturnFixer(MultiFileFix):
    type: Literal["coroutine_return"] = "coroutine_return"
    # error: Return type "... Coroutine[Any, Any, X] ..." of "method" incompatible with
    #        return type "X" in supertype "pkg.module.ClassName"  [override]
    _RETURN_INCOMPATIBLE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: Return type "(?P<full_type>[^"]+)" '
        r'of "(?P<method>[^"]+)" incompatible with return type "(?P<expected>[^"]+)" '
        r'in supertype "(?P<supertype>[^"]+)"'
    )
    # Pull the Coroutine[...] part out of a potentially wider expression
    _COROUTINE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"Coroutine\[(?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*\]"
    )
    # error: Incompatible types in assignment (expression has type
    #        "Callable[[...], Coroutine[Any, Any, X]]", base class "ClassName"
    #        defined the type as "Callable[[...], X]")  [assignment]
    _ASSIGNMENT_RE: ClassVar[re.Pattern[str]] = re.compile(
        r":(?P<line>\d+): error: Incompatible types in assignment "
        r'\(expression has type "(?P<expr>[^"]*Coroutine[^"]*)", '
        r'base class "(?P<base_class>[^"]+)" '
        r'defined the type as "[^"]*"\)'
    )

    @staticmethod
    def _parse_fixes(
        errors_by_file: dict[Path, list[str]],
    ) -> dict[tuple[str, str], str]:
        """Return {(supertype_qualname, method): coroutine_type_str} from [override] errors."""
        fixes: dict[tuple[str, str], str] = {}
        for errors in errors_by_file.values():
            for error in errors:
                m = CoroutineReturnFixer._RETURN_INCOMPATIBLE_RE.search(error)
                if not m:
                    continue
                coro_m = CoroutineReturnFixer._COROUTINE_RE.search(
                    m.group("full_type")
                )
                if not coro_m:
                    continue
                key = (m.group("supertype"), m.group("method"))
                if key not in fixes:
                    fixes[key] = coro_m.group(0)
        return fixes

    @staticmethod
    def _assignment_target_at(tree: ast.Module, lineno: int) -> str | None:
        """Return the name of the assignment target on `lineno`, if it's a simple name."""
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and node.lineno == lineno
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                return node.targets[0].id
        return None

    @staticmethod
    def _parse_assignment_fixes(
        errors_by_file: dict[Path, list[str]],
    ) -> dict[tuple[Path, str, str], str]:
        """Return {(file, base_class, method): coroutine_type} from [assignment] Coroutine errors."""
        fixes: dict[tuple[Path, str, str], str] = {}
        for pyi, errors in errors_by_file.items():
            try:
                text = pyi.read_text()
                tree = ast.parse(text)
            except (OSError, SyntaxError):
                continue
            for error in errors:
                m = CoroutineReturnFixer._ASSIGNMENT_RE.search(error)
                if not m:
                    continue
                coro_m = CoroutineReturnFixer._COROUTINE_RE.search(
                    m.group("expr")
                )
                if not coro_m:
                    continue
                lineno = int(m.group("line"))
                base_class = m.group("base_class")
                method = CoroutineReturnFixer._assignment_target_at(
                    tree, lineno
                )
                if method is None:
                    continue
                key = (pyi, base_class, method)
                if key not in fixes:
                    fixes[key] = coro_m.group(0)
        return fixes

    @staticmethod
    def _find_stub_for_module(
        module: str, reference_path: Path
    ) -> Path | None:
        """Walk up from reference_path to find <root>/<module/as/path>.pyi."""
        relative = Path(*module.split(".")).with_suffix(".pyi")
        candidate = reference_path.parent
        while True:
            target = candidate / relative
            if target.exists():
                return target
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent
        return None

    @staticmethod
    def _find_class_module(
        class_name: str, pyi: Path, stubs_dir: Path
    ) -> tuple[Path, str] | None:
        """Find the stub path and module for `class_name` imported in `pyi`."""
        try:
            tree = ast.parse(pyi.read_text())
        except (OSError, SyntaxError):
            return None
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name == class_name or alias.asname == class_name:
                        stub = CoroutineReturnFixer._find_stub_for_module(
                            node.module, pyi
                        )
                        if stub is not None:
                            return stub, node.module
        return None

    @staticmethod
    def _ensure_imports(
        tree: ast.Module, names: list[str], module: str
    ) -> None:
        """Add 'from <module> import <names>' for any name not already imported."""
        already: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == module:
                already.update(a.name for a in node.names)
        missing = [n for n in names if n not in already]
        if not missing:
            return
        new_import = ast.ImportFrom(
            module=module,
            names=[ast.alias(name=n) for n in missing],
            level=0,
        )
        insert_at = 0
        for i, node in enumerate(tree.body):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_at = i + 1
        tree.body.insert(insert_at, new_import)

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(
            (
                self._RETURN_INCOMPATIBLE_RE.search(e)
                and self._COROUTINE_RE.search(e)
            )
            or self._ASSIGNMENT_RE.search(e)
            for e in errors
        )

    def __call__(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None:
        if not errors_by_file:
            return

        # Handle [override] Return type errors
        fixes = self._parse_fixes(errors_by_file)
        if fixes:
            any_pyi = next(iter(errors_by_file))
            by_parent: dict[str, dict[str, str]] = {}
            for (supertype, method), coro in fixes.items():
                by_parent.setdefault(supertype, {})[method] = coro

            for supertype_qualname, method_fixes in by_parent.items():
                parts = supertype_qualname.rsplit(".", 1)
                if len(parts) != 2:
                    continue
                module, class_name = parts
                parent_path = self._find_stub_for_module(module, any_pyi)
                if parent_path is None:
                    continue
                self._widen_parent(
                    parent_path, class_name, method_fixes, stubs_dir
                )

        # Handle [assignment] Callable[..., Coroutine] errors
        assignment_fixes = self._parse_assignment_fixes(errors_by_file)
        for (pyi, base_class, method), coro in assignment_fixes.items():
            found = self._find_class_module(base_class, pyi, stubs_dir)
            if found is None:
                continue
            parent_path, _ = found
            self._widen_parent(
                parent_path, base_class, {method: coro}, stubs_dir
            )

    def _widen_parent(
        self,
        parent_path: Path,
        class_name: str,
        method_fixes: dict[str, str],
        stubs_dir: Path,
    ) -> None:
        tree = ast.parse(parent_path.read_text())

        expr_fixes: dict[str, ast.expr] = {}
        for method, coro_str in method_fixes.items():
            try:
                expr_fixes[method] = ast.parse(coro_str, mode="eval").body
            except SyntaxError:
                continue

        widener = _ReturnWidener(class_name, expr_fixes)
        tree = widener.visit(tree)
        if not widener.changed:
            return

        self._ensure_imports(tree, ["Any", "Coroutine"], "typing")
        ast.fix_missing_locations(tree)
        parent_path.write_text(ast.unparse(tree))

        # Propagate up: if widening caused new override errors in the parent,
        # fix those too recursively.
        upstream_errors = Mypy().generate([parent_path], stubs_dir)
        if upstream_errors:
            upstream_fixes = self._parse_fixes(upstream_errors)
            by_grandparent: dict[str, dict[str, str]] = {}
            for (supertype, method), coro in upstream_fixes.items():
                by_grandparent.setdefault(supertype, {})[method] = coro
            for supertype_qualname, gp_method_fixes in by_grandparent.items():
                parts = supertype_qualname.rsplit(".", 1)
                if len(parts) != 2:
                    continue
                gp_module, gp_class = parts
                gp_path = self._find_stub_for_module(gp_module, parent_path)
                if gp_path is None:
                    continue
                self._widen_parent(
                    gp_path, gp_class, gp_method_fixes, stubs_dir
                )
