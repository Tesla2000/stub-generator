from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple
from stub_adder.input.types import InputType


class ExistingStubsReader(BaseModel):
    """Yields _StubTuples by pairing .pyi files in stubs_dir with the
    corresponding .py sources in sources_dir, preserving relative structure."""

    model_config = ConfigDict(frozen=True)

    type: Literal[InputType.EXISTING_STUBS] = InputType.EXISTING_STUBS
    stubs_dir: Path
    sources_dir: Path
    logger: PydanticLogger = Field(
        default_factory=lambda: PydanticLogger(name=__name__)
    )

    def generate(self, output_path: Path) -> Iterable[_StubTuple]:
        for pyi_path in self.stubs_dir.rglob("*.pyi"):
            relative = pyi_path.relative_to(self.stubs_dir)
            py_path = self.sources_dir / relative.with_suffix(".py")
            if not py_path.exists():
                self.logger.debug(f"No source found for {pyi_path}, skipping")
                continue
            yield _StubTuple(
                py_path=py_path.absolute(), pyi_path=pyi_path.absolute()
            )
