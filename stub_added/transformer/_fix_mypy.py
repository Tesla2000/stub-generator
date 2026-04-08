from collections import defaultdict
from pathlib import Path
from typing import Annotated
from typing import Literal
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from stub_added._stub_tuple import _StubTuple
from stub_added.transformer._stub_tuples import _StubTuples
from stub_added.transformer._topo import pyi_to_deps
from stub_added.transformer._topo import topo_layers
from stub_added.transformer.error_generator import AnyGenerator
from stub_added.transformer.error_generator import Mypy
from stub_added.transformer.error_generator import Pyright
from stub_added.transformer.file_fix import AbstractClassFixer
from stub_added.transformer.file_fix import CallableToAsyncDef
from stub_added.transformer.file_fix import ImportFixer
from stub_added.transformer.file_fix import LspViolationFixer
from stub_added.transformer.file_fix import MroConflictFixer
from stub_added.transformer.multifile_fixes import AnyBaseFixer
from stub_added.transformer.multifile_fixes import CoroutineReturnFixer
from stub_added.transformer.multifile_fixes import LlmFixer
from stub_added.transformer.transformer_type import TransformerType
from tqdm import tqdm

AnyFix = Annotated[
    Union[
        LspViolationFixer,
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


class FixMypy(BaseModel):
    type: Literal[TransformerType.FIX_MYPY] = TransformerType.FIX_MYPY
    error_generators: tuple[AnyGenerator, ...] = (Mypy(), Pyright())
    fixes: tuple[AnyFix, ...] = Field(
        default_factory=lambda: (
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

    def transform(
        self, stub_tuples: _StubTuples, stubs_dir: Path
    ) -> _StubTuples:
        self._fix_stubs(stub_tuples, stubs_dir)
        return stub_tuples

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
                (
                    fix
                    for fix in self.fixes
                    if not fix.is_applicable(all_errors)
                ),
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
