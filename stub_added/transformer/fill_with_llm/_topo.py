import ast
import os
from collections.abc import Collection
from pathlib import Path

from stub_added._stub_tuple import _StubTuple


def build_module_map(
    stub_tuples: Collection[_StubTuple],
) -> dict[str, _StubTuple]:
    """Map dotted module name → stub tuple, derived from py_path structure."""
    common = Path(os.path.commonpath([s.py_path for s in stub_tuples]))
    if common.is_file():
        common = common.parent
    root = common.parent

    def _mod(py: Path) -> str:
        parts = py.relative_to(root).with_suffix("").parts
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    return {_mod(s.py_path): s for s in stub_tuples}


def internal_imports(
    py_path: Path, module_to_stub: dict[str, _StubTuple]
) -> set[str]:
    """Return module names (keys of module_to_stub) imported by py_path."""
    tree = ast.parse(py_path.read_text())
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in module_to_stub:
                    deps.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if full in module_to_stub:
                    deps.add(full)
                elif node.module in module_to_stub:
                    deps.add(node.module)
    return deps


def pyi_to_deps(
    stub_tuples: Collection[_StubTuple],
) -> dict[Path, set[Path]]:
    """Map each stub's pyi_path to the pyi_paths it directly depends on."""
    if not stub_tuples:
        return {}
    module_to_stub = build_module_map(stub_tuples)
    return {
        s.pyi_path: {
            module_to_stub[m].pyi_path
            for m in internal_imports(s.py_path, module_to_stub)
        }
        for s in stub_tuples
    }


def topo_layers(
    stub_tuples: Collection[_StubTuple],
) -> list[list[_StubTuple]]:
    """Return stub_tuples grouped into topological layers (leaves first)."""
    if not stub_tuples:
        return []

    module_to_stub = build_module_map(stub_tuples)
    mod_by_path = {t.pyi_path: m for m, t in module_to_stub.items()}
    stub_by_path = {s.pyi_path: s for s in stub_tuples}

    remaining: dict[Path, set[str]] = {
        s.pyi_path: internal_imports(s.py_path, module_to_stub)
        for s in stub_tuples
    }
    mod_to_path = {mod: path for path, mod in mod_by_path.items()}

    layers: list[list[_StubTuple]] = []
    while remaining:
        ready = [path for path, deps in remaining.items() if not deps]
        if not ready:
            ready = find_cycle(remaining, mod_to_path)
        layers.append([stub_by_path[p] for p in ready])
        done_mods = {mod_by_path[p] for p in ready}
        for path in ready:
            del remaining[path]
        for deps in remaining.values():
            deps -= done_mods

    return layers


def find_cycle(
    remaining: dict[Path, set[str]], mod_to_path: dict[str, Path]
) -> list[Path]:
    """Return the paths that form one minimal cycle in the dependency graph."""
    adj: dict[Path, list[Path]] = {
        path: [mod_to_path[m] for m in deps if m in mod_to_path]
        for path, deps in remaining.items()
    }

    visited: set[Path] = set()
    stack: list[Path] = []
    on_stack: set[Path] = set()

    def dfs(node: Path) -> list[Path] | None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for neighbour in adj.get(node, []):
            if neighbour not in remaining:
                continue
            if neighbour in on_stack:
                return stack[stack.index(neighbour) :]
            if neighbour not in visited:
                result = dfs(neighbour)
                if result is not None:
                    return result
        stack.pop()
        on_stack.discard(node)
        return None

    for start in remaining:
        if start not in visited:
            cycle = dfs(start)
            if cycle is not None:
                return cycle

    return list(remaining.keys())
