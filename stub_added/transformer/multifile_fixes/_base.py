from abc import abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from stub_added._stub_tuple import _StubTuple


class MultiFileFix(BaseModel):
    scope: Literal["multifile"] = "multifile"

    @abstractmethod
    def __call__(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None: ...
