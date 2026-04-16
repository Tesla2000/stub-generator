from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel, PositiveInt

from stub_adder._stub_tuple import _StubTuple


class SourceSpan(NamedTuple):
    """A replacement span within a single source line (all 0-based)."""

    lineno: int
    start: int
    end: int


class DocstringRange(NamedTuple):
    """Line range of a docstring node (1-based, inclusive)."""

    start: int
    end: int
    only: bool  # True when the docstring is the sole statement in its body


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
