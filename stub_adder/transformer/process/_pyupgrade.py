import subprocess
from pathlib import Path
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class Pyupgrade(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["pyupgrade"] = "pyupgrade"
    min_version: tuple[int, int] = (3, 10)

    def process(self, pyi_paths: list[Path]) -> None:
        """Run pyupgrade on the given stub files in-place."""
        version_flag = f"--py{''.join(map(str, self.min_version))}-plus"
        subprocess.run(
            ["pyupgrade", version_flag] + list(map(str, pyi_paths)),
        )
