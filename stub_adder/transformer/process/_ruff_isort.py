import subprocess
from pathlib import Path
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class RuffIsort(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["ruff_isort"] = "ruff_isort"

    def process(self, pyi_paths: list[Path]) -> None:
        """Run ruff --fix --select I to sort imports in-place."""
        subprocess.run(
            ("ruff", "check", "--fix", "--select", "I")
            + tuple(map(str, pyi_paths)),
            capture_output=True,
        )
