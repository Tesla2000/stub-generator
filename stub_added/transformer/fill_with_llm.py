import ast
import os
from collections.abc import Collection
from pathlib import Path
from typing import TypeVar

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from pydantic import Field
from stub_added._stub_tuple import _StubTuple

_StubTuples = TypeVar("_StubTuples", bound=Collection[_StubTuple])


class FillWithLLM(BaseModel):
    chat_model: ChatGoogleGenerativeAI = Field(
        default_factory=lambda: ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", temperature=0
        )
    )

    def transform(self, stub_tuples: _StubTuples) -> _StubTuples:
        class StubOutput(BaseModel):
            stub_path: Path
            stub_contents: str

        class OutputSchema(BaseModel):
            stub_outputs: list[StubOutput]

        completed: dict[Path, str] = {}

        for layer in self._topo_layers(stub_tuples):
            missing = set(s.pyi_path for s in layer)
            while missing:
                context_parts = []
                for s in stub_tuples:
                    if s.pyi_path in completed:
                        context_parts.append(
                            f"Completed stub (for reference):\nStub path:{s.pyi_path}"
                            f"\n\nStub contents:\n{completed[s.pyi_path]}"
                        )
                    elif s.pyi_path in missing:
                        context_parts.append(
                            f"Original file:\n{s.py_path.read_text()}"
                            f"\n\nStub path:{s.pyi_path}"
                            f"\n\nStub contents:\n{s.pyi_path.read_text()}"
                        )

                output_files = self.chat_model.with_structured_output(
                    OutputSchema
                ).invoke(
                    [
                        SystemMessage(
                            "Fill missing type hints in stub files based on original files. "
                            "You must provide type hinting to each variable, field, argument, "
                            "keyword argument and function return value, Any if can't be decided, "
                            "Self if self. Remove unused imports. "
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

        # Use py_paths to derive module names so they match the actual import
        # statements in source code (e.g. "google.auth.credentials", not just
        # "auth.credentials"). commonpath gives the top-level package directory;
        # its parent is the root that Python's import system would use.
        common = Path(os.path.commonpath([s.py_path for s in stub_tuples]))
        if common.is_file():
            common = common.parent
        root = common.parent

        def _module_name(py_path: Path) -> str:
            parts = py_path.relative_to(root).with_suffix("").parts
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts)

        module_to_stub: dict[str, _StubTuple] = {
            _module_name(s.py_path): s for s in stub_tuples
        }
        mod_by_path = {
            s.pyi_path: _module_name(s.py_path) for s in stub_tuples
        }
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
