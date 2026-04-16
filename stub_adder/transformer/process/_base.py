from abc import abstractmethod
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ProcessBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @abstractmethod
    def process(self, pyi_paths: list[Path]) -> None: ...
