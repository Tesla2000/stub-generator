from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple


class ExistingStubsReader(BaseModel):
    """Yields _StubTuples by pairing .pyi files in stubs_dir with the
    corresponding .py sources in sources_dir, preserving relative structure."""

    model_config = ConfigDict(frozen=True)

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
