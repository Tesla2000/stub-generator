import subprocess
import textwrap
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated
from typing import ClassVar
from typing import Literal
from typing import Union

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic_logger import PydanticLogger
from tqdm import tqdm

from stub_adder._stub_tuple import _StubTuple
from stub_adder.transformer._stub_tuples import _StubTuples
from stub_adder.transformer._topo import pyi_to_deps
from stub_adder.transformer._topo import topo_layers
from stub_adder.transformer.error_generator import AnyGenerator
from stub_adder.transformer.error_generator import Flake8
from stub_adder.transformer.error_generator import Incomplete
from stub_adder.transformer.error_generator import Mypy
from stub_adder.transformer.error_generator import Pyright
from stub_adder.transformer.error_generator import Ruff
from stub_adder.transformer.error_generator import Stubtest
from stub_adder.transformer.file_fix import AbstractClassFixer
from stub_adder.transformer.file_fix import AsyncDefStubFixer
from stub_adder.transformer.file_fix import CallableToAsyncDef
from stub_adder.transformer.file_fix import ClassmethodFixer
from stub_adder.transformer.file_fix import DefaultValueFixer
from stub_adder.transformer.file_fix import DocstringFixer
from stub_adder.transformer.file_fix import EnterReturnSelfFixer
from stub_adder.transformer.file_fix import ImportFixer
from stub_adder.transformer.file_fix import IntFloatFixer
from stub_adder.transformer.file_fix import LongLiteralFixer
from stub_adder.transformer.file_fix import MroConflictFixer
from stub_adder.transformer.file_fix import MutableDefaultFixer
from stub_adder.transformer.file_fix import NotPresentAtRuntimeFixer
from stub_adder.transformer.file_fix import PyrightAttributeFixer
from stub_adder.transformer.file_fix import RemoveDefaultFixer
from stub_adder.transformer.file_fix import RemoveExtraParamFixer
from stub_adder.transformer.file_fix import TypeAliasFixer
from stub_adder.transformer.file_fix import TypeCheckingFixer
from stub_adder.transformer.multifile_fixes import AnyBaseFixer
from stub_adder.transformer.multifile_fixes import CoroutineReturnFixer
from stub_adder.transformer.multifile_fixes import LlmFixer
from stub_adder.transformer.multifile_fixes import LspViolationFixer
from stub_adder.transformer.multifile_fixes import MetadataDependencyFixer
from stub_adder.transformer.process import AnyProcess
from stub_adder.transformer.process import Black
from stub_adder.transformer.process import Pyupgrade
from stub_adder.transformer.process import RuffFix
from stub_adder.transformer.process import StringAnnotationUnquoter
from stub_adder.transformer.process import UnusedImportRemover
from stub_adder.transformer.transformer_type import TransformerType

AnyFix = Annotated[
    Union[
        LspViolationFixer,
        PyrightAttributeFixer,
        ImportFixer,
        MroConflictFixer,
        CallableToAsyncDef,
        AbstractClassFixer,
        AnyBaseFixer,
        CoroutineReturnFixer,
        LlmFixer,
        DocstringFixer,
        TypeAliasFixer,
        TypeCheckingFixer,
        MutableDefaultFixer,
        LongLiteralFixer,
        EnterReturnSelfFixer,
        IntFloatFixer,
        MetadataDependencyFixer,
        AsyncDefStubFixer,
        ClassmethodFixer,
        DefaultValueFixer,
        NotPresentAtRuntimeFixer,
        RemoveDefaultFixer,
        RemoveExtraParamFixer,
    ],
    Field(discriminator="type"),
]


class _ErrorGenerators(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    mypy: Mypy | None = Mypy()
    pyright: Pyright | None = Pyright()
    flake8: Flake8 | None = Flake8()
    ruff: Ruff | None = Ruff()
    stubtest: Stubtest | None = Stubtest()
    incomplete: Incomplete | None = Incomplete()

    def get_generators(self) -> Iterable[AnyGenerator]:
        return filter(None, dict(self).values())


class FixErrors(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal[TransformerType.FIX_MYPY] = TransformerType.FIX_MYPY
    error_generators: _ErrorGenerators = _ErrorGenerators()
    fixes: tuple[AnyFix, ...] = Field(
        default_factory=lambda: (
            MetadataDependencyFixer(),
            TypeCheckingFixer(),
            DocstringFixer(),
            TypeAliasFixer(),
            MutableDefaultFixer(),
            LongLiteralFixer(),
            EnterReturnSelfFixer(),
            IntFloatFixer(),
            PyrightAttributeFixer(),
            AnyBaseFixer(),
            LspViolationFixer(),
            ImportFixer(),
            MroConflictFixer(),
            CallableToAsyncDef(),
            AbstractClassFixer(),
            AsyncDefStubFixer(),
            ClassmethodFixer(),
            NotPresentAtRuntimeFixer(),
            RemoveExtraParamFixer(),
            RemoveDefaultFixer(),
            DefaultValueFixer(),
            CoroutineReturnFixer(),
            LlmFixer(),
        )
    )
    process: tuple[AnyProcess, ...] = Field(
        default_factory=lambda: (
            UnusedImportRemover(),
            StringAnnotationUnquoter(),
            Pyupgrade(),
            Black(),
            RuffFix(),
        )
    )
    logger: PydanticLogger = PydanticLogger(name=__name__)

    @classmethod
    def _commit_fix(
        cls, stubs_dir: Path, fix_type: str, errors: list[str]
    ) -> None:
        cls._git(stubs_dir, "add", "-A")
        error_summary = textwrap.shorten(
            "; ".join(errors), width=200, placeholder="..."
        )
        message = f"fix({fix_type}): {error_summary}"
        try:
            cls._git(stubs_dir, "commit", "-m", message)
        except subprocess.CalledProcessError:
            pass  # nothing changed — no commit needed

    @staticmethod
    def _git(stubs_dir: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(stubs_dir), *args],
            capture_output=True,
            check=True,
        )

    @classmethod
    def _ensure_git(cls, stubs_dir: Path) -> None:
        if not (stubs_dir / ".git").exists():
            cls._git(stubs_dir, "init")
            cls._git(stubs_dir, "add", "-A")
            cls._git(stubs_dir, "commit", "-m", "Initial stubs")

    def transform(
        self, stub_tuples: _StubTuples, stubs_dir: Path
    ) -> _StubTuples:
        self._ensure_git(stubs_dir)
        completed: dict[Path, str] = {}
        deps = pyi_to_deps(stub_tuples)
        for layer in tqdm(topo_layers(stub_tuples)):
            self._fix_mypy_errors(layer, deps, completed, stubs_dir)
            for s in layer:
                completed[s.pyi_path] = s.pyi_path.read_text()
        return stub_tuples

    def _generate_errors(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        errors_by_file: dict[Path, list[str]] = defaultdict(list)
        for generator in self.error_generators.get_generators():
            for path, errors in generator.generate(
                pyi_paths, stubs_dir
            ).items():
                errors_by_file[path.absolute()].extend(errors)
        return errors_by_file

    def _fix_mypy_errors(
        self,
        layer: list[_StubTuple],
        layer_deps: dict[Path, set[Path]],
        completed: dict[Path, str],
        stubs_dir: Path,
    ) -> None:
        pyi_paths = [s.pyi_path for s in layer]
        stub_by_path = {s.pyi_path.absolute(): s for s in layer}
        attempts: dict[str, int] = {fix.type: 0 for fix in self.fixes}

        for processor in self.process:
            processor.process(pyi_paths)
        prev_all_errors: list[str] = []
        while True:
            file_errors = self._generate_errors(pyi_paths, stubs_dir)
            if not file_errors:
                self.logger.debug(f"Fixed all issues in {layer=}")
                return
            all_errors = [e for errors in file_errors.values() for e in errors]
            if sorted(all_errors) == sorted(prev_all_errors):
                raise ValueError(
                    f"Errors unchanged after applying fix.\n{file_errors=}"
                )
            prev_all_errors = all_errors

            affected_stubs = list(
                filter(None, map(stub_by_path.get, file_errors))
            )

            fix = next(
                (fix for fix in self.fixes if fix.is_applicable(all_errors)),
                None,
            )
            self.logger.debug(f"Using {fix} to fix {file_errors=}")
            if fix is None:
                raise ValueError(f"No fix applicable for {all_errors=}")
            if attempts[fix.type] >= fix.max_attempts:
                raise ValueError(
                    f"Fix {fix.type!r} exhausted {fix.max_attempts} attempts.\n{file_errors=}"
                )
            attempts[fix.type] += 1
            fix.apply(
                affected_stubs,
                file_errors,
                completed,
                layer_deps,
                stubs_dir,
            )
            for processor in self.process:
                processor.process(pyi_paths)
            self._commit_fix(stubs_dir, fix.type, all_errors)
