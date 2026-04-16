from abc import abstractmethod
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic_logger import PydanticLogger


class VersionExtractorBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    logger: PydanticLogger = PydanticLogger(name=__name__)

    @abstractmethod
    def __call__(self, repo_path: Path) -> str | None: ...
