from collections.abc import Iterable
from pathlib import Path
from shutil import copy2
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple


class DirectoryOutput(BaseModel):
    """Copies generated stub files into a local directory."""

    model_config = ConfigDict(frozen=True)

    type: Literal["directory"] = "directory"
    output_dir: Path
    logger: PydanticLogger = PydanticLogger(name=__name__)

    def save(
        self, stub_tuples: Iterable[_StubTuple], stubs_root: Path
    ) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for stub_tuple in stub_tuples:
            relative = stub_tuple.pyi_path.relative_to(stubs_root.absolute())
            target = self.output_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(stub_tuple.pyi_path, target)
            self.logger.debug(f"Copied stub: {target}")
