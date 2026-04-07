from abc import ABC
from abc import abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import PositiveInt
from stub_added._stub_tuple import _StubTuple


class ManualFix(BaseModel, ABC):
    scope: Literal["file"] = "file"
    max_attempts: PositiveInt = 10

    @abstractmethod
    def is_applicable(self, errors: Iterable[str]) -> bool: ...

    @abstractmethod
    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str: ...

    def apply(
        self,
        _: list["_StubTuple"],
        errors_by_file: dict[Path, list[str]],
        __: dict[Path, str],
        ___: dict[Path, set[Path]],
        stubs_dir: Path,
    ) -> None:
        for pyi, errors in errors_by_file.items():
            contents = self(
                contents=pyi.read_text(),
                errors=errors,
                stubs_dir=stubs_dir,
            )
            pyi.write_text(contents)
