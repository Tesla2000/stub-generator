from abc import ABC
from abc import abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import PositiveInt
from stub_added._stub_tuple import _StubTuple


class MultiFileFix(BaseModel, ABC):
    scope: Literal["multifile"] = "multifile"
    max_attempts: PositiveInt = 10

    @abstractmethod
    def is_applicable(self, errors: Iterable[str]) -> bool: ...

    @abstractmethod
    def __call__(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None: ...

    def apply(
        self,
        affected_stubs: list[_StubTuple],
        errors_by_file: dict[Path, list[str]],
        completed: dict[Path, str],
        layer_deps: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None:
        self(affected_stubs, errors_by_file, completed, layer_deps, stubs_dir)
