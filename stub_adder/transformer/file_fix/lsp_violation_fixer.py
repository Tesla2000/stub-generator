import ast
import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix
from stub_adder.transformer.file_fix.import_fixer import ImportFixer


class _ReturnTypeFixer(ast.NodeTransformer):
    def __init__(self, fixes: dict[str, ast.expr]) -> None:
        self._fixes = fixes

    def _fix(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        if node.name in self._fixes:
            node.returns = self._fixes[node.name]
        return node

    visit_FunctionDef = _fix
    visit_AsyncFunctionDef = _fix  # type: ignore[assignment]


class _PositionalFixer(ast.NodeTransformer):
    def __init__(self, fixes: dict[tuple[str, int], ast.expr]) -> None:
        self._fixes = fixes

    def _fix(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        all_args = node.args.posonlyargs + node.args.args
        non_self = (
            all_args[1:]
            if all_args and all_args[0].arg in ("self", "cls")
            else all_args
        )
        for (method, n), new_ann in self._fixes.items():
            if node.name != method:
                continue
            idx = n - 1
            if 0 <= idx < len(non_self):
                non_self[idx].annotation = new_ann
        return node

    visit_FunctionDef = _fix
    visit_AsyncFunctionDef = _fix  # type: ignore[assignment]


class _SignatureFixer(ast.NodeTransformer):
    """Reorder and retype non-self args to match the superclass signature."""

    def __init__(
        self, sig_fixes: dict[str, tuple[ast.arguments, ast.expr | None]]
    ) -> None:
        self._fixes = sig_fixes

    @staticmethod
    def _args_with_defaults(
        node: ast.FunctionDef, self_count: int
    ) -> set[ast.arg]:
        """Return the set of positional args that have default values."""
        all_args = node.args.posonlyargs + node.args.args
        non_self = all_args[self_count:]
        n_defaults = len(node.args.defaults)
        return set(non_self[len(non_self) - n_defaults :])

    def _fix(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        if node.name not in self._fixes:
            return node

        super_args, super_returns = self._fixes[node.name]
        if super_returns is not None:
            node.returns = super_returns
        all_args = node.args.posonlyargs + node.args.args
        self_args = (
            all_args[:1]
            if all_args and all_args[0].arg in ("self", "cls")
            else []
        )
        non_self = all_args[len(self_args) :]

        # If subclass uses *args/**kwargs, replace entire signature with superclass's
        if node.args.vararg is not None or not non_self:
            super_non_self = super_args.args  # already self-stripped
            node.args = super_args
            node.args.posonlyargs = []
            node.args.args = self_args + super_non_self
            return node

        subclass_by_name = {arg.arg: arg for arg in non_self}
        had_default = {
            arg.arg
            for arg in non_self
            if arg in self._args_with_defaults(node, len(self_args))
        }

        super_positional = super_args.posonlyargs + super_args.args
        reordered: list[ast.arg] = []
        for super_arg in super_positional:
            if super_arg.arg not in subclass_by_name:
                continue
            arg = subclass_by_name[super_arg.arg]
            arg.annotation = super_arg.annotation
            reordered.append(arg)

        # Any subclass args absent from superclass go at the end unchanged
        super_names = {a.arg for a in super_positional}
        for arg in non_self:
            if arg.arg not in super_names:
                reordered.append(arg)

        node.args.posonlyargs = []
        node.args.args = self_args + reordered
        default_count = sum(1 for a in reordered if a.arg in had_default)
        node.args.defaults = [ast.Constant(value=...)] * default_count
        return node

    visit_FunctionDef = _fix
    visit_AsyncFunctionDef = _fix  # type: ignore[assignment]


class _FieldFixer(ast.NodeTransformer):
    """Fix AnnAssign and @property return types to match superclass."""

    def __init__(self, fixes: dict[str, ast.expr]) -> None:
        self._fixes = fixes

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign:
        self.generic_visit(node)
        if isinstance(node.target, ast.Name) and node.target.id in self._fixes:
            node.annotation = self._fixes[node.target.id]
        return node

    def _fix(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        if node.name not in self._fixes:
            return node
        # Only fix if it's a property (has @property decorator)
        is_property = any(
            (isinstance(d, ast.Name) and d.id == "property")
            or (isinstance(d, ast.Attribute) and d.attr == "property")
            for d in node.decorator_list
        )
        if is_property:
            node.returns = self._fixes[node.name]
        return node

    visit_FunctionDef = _fix
    visit_AsyncFunctionDef = _fix  # type: ignore[assignment]


class LspViolationFixer(ManualFix):
    type: Literal["lsp"] = "lsp"
    # Format 1: per-argument errors
    _ARG_RE: ClassVar[re.Pattern[str]] = re.compile(
        r':\d+: error: Argument (?P<n>\d+) of "(?P<method>[^"]+)" '
        r"is incompatible with supertype \"[^\"]+\"; "
        r'supertype defines the argument type as "(?P<expected>[^"]+)"'
    )
    # Format 2: full-signature errors
    _SIG_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: Signature of "(?P<method>[^"]+)" incompatible with supertype'
    )
    _DEF_NOTE_RE: ClassVar[re.Pattern[str]] = re.compile(r"note:\s+def \w+\(")
    _TYPE_NOTE_RE: ClassVar[re.Pattern[str]] = re.compile(r"note:\s+\S")
    # Format 3: return type errors
    _RETURN_RE: ClassVar[re.Pattern[str]] = re.compile(
        r'error: Return type "[^"]+" of "(?P<method>[^"]+)" incompatible with '
        r'return type "(?P<expected>[^"]+)" in supertype'
    )

    @staticmethod
    def _parse_return_fixes(errors: list[str]) -> dict[str, ast.expr]:
        """Format 3: method → supertype return annotation (first supertype wins)."""
        fixes: dict[str, ast.expr] = {}
        for error in errors:
            m = LspViolationFixer._RETURN_RE.search(error)
            if not m:
                continue
            method = m.group("method")
            if method in fixes:
                continue
            try:
                fixes[method] = ast.parse(
                    m.group("expected"), mode="eval"
                ).body
            except SyntaxError:
                pass
        return fixes

    @staticmethod
    def _parse_positional_fixes(
        errors: list[str],
    ) -> dict[tuple[str, int], ast.expr]:
        """Format 1: (method, arg_n) → supertype annotation."""
        fixes: dict[tuple[str, int], ast.expr] = {}
        for error in errors:
            m = LspViolationFixer._ARG_RE.search(error)
            if not m:
                continue
            key = (m.group("method"), int(m.group("n")))
            if key in fixes:
                continue
            try:
                fixes[key] = ast.parse(m.group("expected"), mode="eval").body
            except SyntaxError:
                pass
        return fixes

    @staticmethod
    def _parse_signature_fixes(
        errors: list[str],
    ) -> dict[str, tuple[ast.arguments, ast.expr | None]]:
        """Format 2: method → (superclass ast.arguments self-stripped, return annotation)."""
        result: dict[str, tuple[ast.arguments, ast.expr | None]] = {}
        seen: set[str] = set()
        i = 0
        while i < len(errors):
            sig_m = LspViolationFixer._SIG_RE.search(errors[i])
            if not sig_m:
                i += 1
                continue
            method = sig_m.group("method")
            j = i + 1
            while j < len(errors) and not LspViolationFixer._SIG_RE.search(
                errors[j]
            ):
                if "Superclass:" in errors[j]:
                    if j + 1 < len(
                        errors
                    ) and LspViolationFixer._DEF_NOTE_RE.search(errors[j + 1]):
                        def_line = re.sub(
                            r"^[^:]+:\d+: note:\s+", "", errors[j + 1]
                        ).strip()
                        if method not in seen:
                            seen.add(method)
                            try:
                                tree = ast.parse(
                                    f"{def_line}: ...", mode="exec"
                                )
                                func = tree.body[0]
                                assert isinstance(func, ast.FunctionDef)
                                args = func.args
                                returns = func.returns
                                # Strip self/cls from positional args
                                all_pos = args.posonlyargs + args.args
                                if all_pos and all_pos[0].arg in (
                                    "self",
                                    "cls",
                                ):
                                    if args.posonlyargs:
                                        args.posonlyargs = args.posonlyargs[1:]
                                    else:
                                        args.args = args.args[1:]
                                    # Trim defaults to match remaining positional args
                                    remaining = len(args.posonlyargs) + len(
                                        args.args
                                    )
                                    if len(args.defaults) > remaining:
                                        args.defaults = args.defaults[
                                            -remaining:
                                        ]
                                result[method] = (args, returns)
                            except SyntaxError:
                                pass
                    break
                j += 1
            i += 1
        return result

    @staticmethod
    def _parse_field_fixes(errors: list[str]) -> dict[str, ast.expr]:
        """Format 4: field/property name → supertype annotation (non-def signature mismatch)."""
        result: dict[str, ast.expr] = {}
        i = 0
        while i < len(errors):
            sig_m = LspViolationFixer._SIG_RE.search(errors[i])
            if not sig_m:
                i += 1
                continue
            name = sig_m.group("method")
            j = i + 1
            while j < len(errors) and not LspViolationFixer._SIG_RE.search(
                errors[j]
            ):
                if "Superclass:" in errors[j]:
                    candidate = j + 1
                    if (
                        candidate < len(errors)
                        and LspViolationFixer._TYPE_NOTE_RE.search(
                            errors[candidate]
                        )
                        and not LspViolationFixer._DEF_NOTE_RE.search(
                            errors[candidate]
                        )
                    ):
                        type_str = re.sub(
                            r"^[^:]+:\d+: note:\s+", "", errors[candidate]
                        ).strip()
                        if name not in result:
                            try:
                                result[name] = ast.parse(
                                    type_str, mode="eval"
                                ).body
                            except SyntaxError:
                                pass
                    break
                j += 1
            i += 1
        return result

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(
            self._ARG_RE.search(e)
            or self._SIG_RE.search(e)
            or (self._RETURN_RE.search(e) and "Coroutine" not in e)
            for e in errors
        )

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        positional = self._parse_positional_fixes(errors)
        named = self._parse_signature_fixes(errors)
        returns = self._parse_return_fixes(errors)
        all_field_fixes = self._parse_field_fixes(errors)
        # Exclude names already handled as method signatures
        fields = {k: v for k, v in all_field_fixes.items() if k not in named}

        if not positional and not named and not returns and not fields:
            return contents

        tree = ast.parse(contents)
        if positional:
            tree = _PositionalFixer(positional).visit(tree)
        if named:
            tree = _SignatureFixer(named).visit(tree)
        if returns:
            tree = _ReturnTypeFixer(returns).visit(tree)
        if fields:
            tree = _FieldFixer(fields).visit(tree)
        ast.fix_missing_locations(tree)
        return ImportFixer.resolve_annotation_imports(
            ast.unparse(tree), errors, stubs_dir
        )
