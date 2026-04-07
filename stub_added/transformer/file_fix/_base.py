from abc import abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class ManualFix(BaseModel):
    scope: Literal["file"] = "file"

    @abstractmethod
    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str: ...
