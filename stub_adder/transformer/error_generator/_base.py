from abc import abstractmethod
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ErrorGeneratorBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @abstractmethod
    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]: ...
