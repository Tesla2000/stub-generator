import ast
import os
from collections.abc import Collection
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from pydantic import Field
from stub_added._stub_tuple import _StubTuple
from stub_added.transformer._stub_tuples import _StubTuples
from tqdm import tqdm


class FillWithLLM(BaseModel):
    chat_model: ChatGoogleGenerativeAI = Field(
        default_factory=lambda: ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite", temperature=0
        )
    )

    def transform(self, stub_tuples: _StubTuples) -> _StubTuples:
        class StubOutput(BaseModel):
            stub_path: Path
            stub_contents: str

        class OutputSchema(BaseModel):
            stub_outputs: list[StubOutput]

        completed: dict[Path, str] = {}
        pyi_to_deps = self._pyi_to_deps(stub_tuples)

        for layer in tqdm(self._topo_layers(stub_tuples)):
            missing = set(s.pyi_path for s in layer)
            while missing:
                # Collect completed stubs that are direct imports of this layer
                needed_completed: set[Path] = {
                    dep
                    for s in layer
                    for dep in pyi_to_deps.get(s.pyi_path, set())
                    if dep in completed
                }

                context_parts = []
                for pyi, contents in completed.items():
                    if pyi in needed_completed:
                        context_parts.append(
                            f"Completed stub (for reference):\nStub path:{pyi}"
                            f"\nStub contents:\n{contents}"
                        )
                for s in layer:
                    context_parts.append(
                        f"Original file:\n{s.py_path.read_text()}"
                        f"\n\nStub path:{s.pyi_path}"
                        f"\nStub contents:\n{s.pyi_path.read_text()}"
                    )

                output_files = self.chat_model.with_structured_output(
                    OutputSchema
                ).invoke(
                    [
                        SystemMessage(
                            "Fill missing type hints in stub files based on original files. "
                            "You must provide type hinting to each variable, field, argument, "
                            "keyword argument and function return value, Any if can't be decided, "
                            "Self if self. Remove unused imports and add missing imports. "
                            f"Return a list of {StubOutput.__name__} objects where stub_path "
                            "corresponds to original stub file and contents is version with all "
                            "type hints present. Return contents for all Stub paths even if they "
                            "don't require changes"
                        ),
                        HumanMessage(
                            "\n\n".join(context_parts)
                            + f"\n\n\nHere is a list of stub output paths you need to return "
                            f"{StubOutput.__name__} for: "
                            + ", ".join(
                                str(s.pyi_path)
                                for s in layer
                                if s.pyi_path in missing
                            )
                        ),
                    ]
                )

                stub_outputs: list[StubOutput] = output_files.stub_outputs
                for output in stub_outputs:
                    if output.stub_path not in missing:
                        continue
                    output.stub_path.write_text(output.stub_contents)
                    completed[output.stub_path] = output.stub_contents
                missing -= {output.stub_path for output in stub_outputs}

        return stub_tuples

    @classmethod
    def _pyi_to_deps(
        cls, stub_tuples: Collection[_StubTuple]
    ) -> dict[Path, set[Path]]:
        """Map each stub's pyi_path to the pyi_paths it directly depends on."""
        if not stub_tuples:
            return {}
        module_to_stub = cls._build_module_map(stub_tuples)
        return {
            s.pyi_path: {
                module_to_stub[m].pyi_path
                for m in cls._internal_imports(s.py_path, module_to_stub)
            }
            for s in stub_tuples
        }

    @staticmethod
    def _build_module_map(
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

    @staticmethod
    def _internal_imports(
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

    @classmethod
    def _topo_layers(
        cls, stub_tuples: Collection[_StubTuple]
    ) -> list[list[_StubTuple]]:
        """Return stub_tuples grouped into topological layers (leaves first)."""
        if not stub_tuples:
            return []

        module_to_stub = cls._build_module_map(stub_tuples)
        mod_by_path = {t.pyi_path: m for m, t in module_to_stub.items()}
        stub_by_path = {s.pyi_path: s for s in stub_tuples}

        remaining: dict[Path, set[str]] = {
            s.pyi_path: cls._internal_imports(s.py_path, module_to_stub)
            for s in stub_tuples
        }

        mod_to_path = {mod: path for path, mod in mod_by_path.items()}

        layers: list[list[_StubTuple]] = []
        while remaining:
            ready = [path for path, deps in remaining.items() if not deps]
            if not ready:
                ready = _find_cycle(remaining, mod_to_path)
            layers.append([stub_by_path[p] for p in ready])
            done_mods = {mod_by_path[p] for p in ready}
            for path in ready:
                del remaining[path]
            for deps in remaining.values():
                deps -= done_mods

        return layers


def _find_cycle(
    remaining: dict[Path, set[str]], mod_to_path: dict[str, Path]
) -> list[Path]:
    """Return the paths that form one minimal cycle in the dependency graph."""
    # Build a path → {dependent paths} adjacency from the remaining module deps.
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
                # Found cycle – slice from the cycle entry point
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

    return list(remaining.keys())  # unreachable if there truly is a cycle
