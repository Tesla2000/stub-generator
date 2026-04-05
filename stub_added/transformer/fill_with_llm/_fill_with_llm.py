from pathlib import Path
from typing import Annotated
from typing import Literal
from typing import Union

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from pydantic import Discriminator
from pydantic import Field
from pydantic import PositiveInt
from pydantic import Tag
from stub_added._stub_tuple import _StubTuple
from stub_added.transformer._stub_tuples import _StubTuples
from stub_added.transformer.fill_with_llm._mypy import run_mypy
from stub_added.transformer.fill_with_llm._provider import get_provider
from stub_added.transformer.fill_with_llm._provider import Provider
from stub_added.transformer.fill_with_llm._schema import _OutputSchema
from stub_added.transformer.fill_with_llm._schema import _STUB_RULES
from stub_added.transformer.fill_with_llm._schema import _StubOutput
from stub_added.transformer.fill_with_llm._schema import _StubOutputPath
from stub_added.transformer.fill_with_llm._topo import pyi_to_deps
from stub_added.transformer.fill_with_llm._topo import topo_layers
from stub_added.transformer.fill_with_llm.manual_fixes import AnyManualFix
from stub_added.transformer.fill_with_llm.manual_fixes import (
    DEFAULT_MANUAL_FIXES,
)
from stub_added.transformer.transformer_type import TransformerType
from tqdm import tqdm


class FillWithLLM(BaseModel):
    type: Literal[TransformerType.FILL_WITH_LLM] = (
        TransformerType.FILL_WITH_LLM
    )
    chat_model: Annotated[
        Union[
            Annotated[ChatGoogleGenerativeAI, Tag(Provider.GEMINI)],
            Annotated[ChatOpenAI, Tag(Provider.OPENAI)],
        ],
        Discriminator(get_provider),
    ] = Field(
        default_factory=lambda: ChatOpenAI(model="gpt-5-nano", temperature=0)
    )
    max_mypy_fix_iterations: PositiveInt = 5
    manual_fixes: tuple[AnyManualFix, ...] = Field(
        default=DEFAULT_MANUAL_FIXES
    )

    def transform(
        self, stub_tuples: _StubTuples, stubs_dir: Path
    ) -> _StubTuples:
        self._fill_stubs(stub_tuples, stubs_dir)
        return stub_tuples

    def _fill_stubs(self, stub_tuples: _StubTuples, stubs_dir: Path) -> None:
        completed: dict[Path, str] = {}
        deps = pyi_to_deps(stub_tuples)
        for layer in tqdm(topo_layers(stub_tuples)):
            self._fix_mypy_errors(layer, deps, completed, stubs_dir)
            for s in layer:
                completed[s.pyi_path] = s.pyi_path.read_text()

    def _fix_mypy_errors(
        self,
        layer: list[_StubTuple],
        layer_deps: dict[Path, set[Path]],
        completed: dict[Path, str],
        stubs_dir: Path,
    ) -> None:
        pyi_paths = [s.pyi_path for s in layer]
        stub_by_path = {s.pyi_path: s for s in layer}

        for _ in range(self.max_mypy_fix_iterations):
            errors_by_file = run_mypy(pyi_paths, stubs_dir)
            if not errors_by_file:
                return

            for pyi, errors in errors_by_file.items():
                contents = pyi.read_text()
                for fix in self.manual_fixes:
                    contents = fix(contents, errors)
                    pyi.write_text(contents)
                    errors = run_mypy([pyi], stubs_dir).get(pyi, [])
                    if not errors:
                        break

            errors_by_file = run_mypy(pyi_paths, stubs_dir)
            if not errors_by_file:
                return

            affected_stubs = list(
                filter(None, map(stub_by_path.get, errors_by_file))
            )
            needed_completed: set[Path] = {
                dep
                for s in affected_stubs
                for dep in layer_deps.get(s.pyi_path, set())
                if dep in completed
            }
            context_parts = [
                f"Completed stub (for reference):\nStub path:{pyi}"
                f"\nStub contents:\n{contents}"
                for pyi, contents in completed.items()
                if pyi in needed_completed
            ] + [
                f"Original file:\n{s.py_path.read_text()}"
                f"\n\nStub path:{s.pyi_path}"
                f"\nStub contents:\n{s.pyi_path.read_text()}"
                f"\n\nMypy errors:\n{chr(10).join(errors_by_file[s.pyi_path])}"
                for s in affected_stubs
            ]
            try:
                stub_outputs = self._invoke_llm(
                    "Fill in missing type hints and fix mypy --strict errors in stub files. "
                    "You are given the original Python file, the current stub contents, "
                    "and the mypy errors describing what is missing or wrong. "
                    "Resolve all errors so the stub passes mypy --strict. "
                    f"Return a list of {_StubOutput.__name__} objects where stub_path "
                    "corresponds to the stub file and contents is the fixed version. "
                    + _STUB_RULES,
                    context_parts,
                    affected_stubs,
                )
            except SyntaxError:
                continue
            for output in stub_outputs:
                if output.stub_path in errors_by_file:
                    output.stub_path.write_text(output.stub_contents)
        raise ValueError(
            f"Failed to fix all mypy issues in {self.max_mypy_fix_iterations} iterations.\n{errors_by_file=}"
        )

    def _invoke_llm(
        self,
        system_message: str,
        context_parts: list[str],
        target_stubs: list[_StubTuple],
    ) -> list[_StubOutputPath]:
        output_files = self.chat_model.with_structured_output(
            _OutputSchema
        ).invoke(
            [
                SystemMessage(system_message),
                HumanMessage(
                    "\n\n".join(context_parts)
                    + f"\n\n\nHere is a list of stub output paths you need to return "
                    f"{_StubOutput.__name__} for: "
                    + ", ".join(str(s.pyi_path) for s in target_stubs)
                ),
            ]
        )
        assert isinstance(output_files, _OutputSchema)
        return list(
            map(_StubOutputPath.from_stub_output, output_files.stub_outputs)
        )
