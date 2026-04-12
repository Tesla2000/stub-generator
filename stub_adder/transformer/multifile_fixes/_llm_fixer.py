from collections.abc import Iterable
from pathlib import Path
from typing import Annotated
from typing import Literal
from typing import Union

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import Discriminator
from pydantic import Field
from pydantic import Tag

from stub_adder._stub_tuple import _StubTuple
from stub_adder.transformer._provider import get_provider
from stub_adder.transformer._provider import Provider
from stub_adder.transformer._schema import _OutputSchema
from stub_adder.transformer._schema import _STUB_RULES
from stub_adder.transformer._schema import _StubOutput
from stub_adder.transformer._schema import _StubOutputPath
from stub_adder.transformer.multifile_fixes._base import MultiFileFix


class LlmFixer(MultiFileFix):
    type: Literal["llm"] = "llm"
    max_attempts: int = 3
    chat_model: Annotated[
        Union[
            Annotated[ChatGoogleGenerativeAI, Tag(Provider.GEMINI)],
            Annotated[ChatOpenAI, Tag(Provider.OPENAI)],
        ],
        Discriminator(get_provider),
    ] = Field(
        default_factory=lambda: ChatOpenAI(model="gpt-5-nano", temperature=0)
    )

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(True for _ in errors)

    def __call__(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None:
        try:
            self._fix(affected_stubs, errors_by_file, completed, layer_deps)
        except SyntaxError:
            pass

    def _fix(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
    ) -> None:
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
        for output in stub_outputs:
            output.stub_path.write_text(output.stub_contents)

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
