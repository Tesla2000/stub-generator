from collections import defaultdict
from pathlib import Path
from typing import Annotated
from typing import Literal
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from tqdm import tqdm

from stub_adder._stub_tuple import _StubTuple
from stub_adder.transformer._stub_tuples import _StubTuples
from stub_adder.transformer._topo import pyi_to_deps
from stub_adder.transformer._topo import topo_layers
from stub_adder.transformer.error_generator import AnyGenerator
from stub_adder.transformer.error_generator import Mypy
from stub_adder.transformer.error_generator import Pyright
from stub_adder.transformer.file_fix import AbstractClassFixer
from stub_adder.transformer.file_fix import CallableToAsyncDef
from stub_adder.transformer.file_fix import ImportFixer
from stub_adder.transformer.file_fix import LspViolationFixer
from stub_adder.transformer.file_fix import MroConflictFixer
from stub_adder.transformer.file_fix import PyrightAttributeFixer
from stub_adder.transformer.multifile_fixes import AnyBaseFixer
from stub_adder.transformer.multifile_fixes import CoroutineReturnFixer
from stub_adder.transformer.multifile_fixes import LlmFixer
from stub_adder.transformer.post_process import AnyPostProcess
from stub_adder.transformer.post_process import Black
from stub_adder.transformer.post_process import Pyupgrade
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
    ],
    Field(discriminator="type"),
]


class FixErrors(BaseModel):
    type: Literal[TransformerType.FIX_MYPY] = TransformerType.FIX_MYPY
    error_generators: tuple[AnyGenerator, ...] = (
        Mypy(),
        Pyright(),
    )
    fixes: tuple[AnyFix, ...] = Field(
        default_factory=lambda: (
            PyrightAttributeFixer(),
            AnyBaseFixer(),
            LspViolationFixer(),
            ImportFixer(),
            MroConflictFixer(),
            CallableToAsyncDef(),
            AbstractClassFixer(),
            CoroutineReturnFixer(),
            LlmFixer(),
        )
    )
    post_process: tuple[AnyPostProcess, ...] = Field(
        default_factory=lambda: (
            Pyupgrade(),
            Black(),
        )
    )

    def transform(
        self, stub_tuples: _StubTuples, stubs_dir: Path
    ) -> _StubTuples:
        self._fix_stubs(stub_tuples, stubs_dir)
        self._run_post_process(stub_tuples)
        return stub_tuples

    def _run_post_process(self, stub_tuples: _StubTuples) -> None:
        pyi_paths = [s.pyi_path for s in stub_tuples]
        for processor in self.post_process:
            processor.process(pyi_paths)

    def _fix_stubs(self, stub_tuples: _StubTuples, stubs_dir: Path) -> None:
        completed: dict[Path, str] = {}
        deps = pyi_to_deps(stub_tuples)
        for layer in tqdm(topo_layers(stub_tuples)):
            self._fix_mypy_errors(layer, deps, completed, stubs_dir)
            for s in layer:
                completed[s.pyi_path] = s.pyi_path.read_text()

    def _generate_errors(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        errors_by_file: dict[Path, list[str]] = defaultdict(list)
        for generator in self.error_generators:
            for path, errors in generator.generate(
                pyi_paths, stubs_dir
            ).items():
                errors_by_file[path].extend(errors)
        return errors_by_file

    def _fix_mypy_errors(
        self,
        layer: list[_StubTuple],
        layer_deps: dict[Path, set[Path]],
        completed: dict[Path, str],
        stubs_dir: Path,
    ) -> None:
        pyi_paths = [s.pyi_path for s in layer]
        stub_by_path = {s.pyi_path: s for s in layer}
        attempts: dict[str, int] = {fix.type: 0 for fix in self.fixes}

        while True:
            errors_by_file = self._generate_errors(pyi_paths, stubs_dir)
            if not errors_by_file:
                return

            all_errors = [
                e for errors in errors_by_file.values() for e in errors
            ]
            affected_stubs = list(
                filter(None, map(stub_by_path.get, errors_by_file))
            )

            fix = next(
                (fix for fix in self.fixes if fix.is_applicable(all_errors)),
                None,
            )
            if fix is None:
                raise ValueError(f"No fix applicable for {all_errors=}")
            if attempts[fix.type] >= fix.max_attempts:
                raise ValueError(
                    f"Fix {fix.type!r} exhausted {fix.max_attempts} attempts.\n{errors_by_file=}"
                )
            attempts[fix.type] += 1
            fix.apply(
                affected_stubs,
                errors_by_file,
                completed,
                layer_deps,
                stubs_dir,
            )
