from pathlib import Path
from typing import Annotated
from typing import Literal
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from pydantic import PositiveInt
from stub_added._stub_tuple import _StubTuple
from stub_added.transformer._mypy import run_mypy
from stub_added.transformer._stub_tuples import _StubTuples
from stub_added.transformer._topo import pyi_to_deps
from stub_added.transformer._topo import topo_layers
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
    max_mypy_fix_iterations: PositiveInt = 5
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

            affected_stubs = list(
                filter(None, map(stub_by_path.get, errors_by_file))
            )
            for fix in self.fixes:
                if fix.scope == "file":
                    for pyi, errors in errors_by_file.items():
                        contents = fix(
                            contents=pyi.read_text(),
                            errors=errors,
                            stubs_dir=stubs_dir,
                        )
                        pyi.write_text(contents)
                else:
                    fix(
                        affected_stubs,
                        errors_by_file,
                        completed,
                        layer_deps,
                        stubs_dir,
                    )

                errors_by_file = run_mypy(pyi_paths, stubs_dir)
                if not errors_by_file:
                    return
                affected_stubs = list(
                    filter(None, map(stub_by_path.get, errors_by_file))
                )

        raise ValueError(
            f"Failed to fix all mypy issues in {self.max_mypy_fix_iterations} iterations.\n{errors_by_file=}"
        )
