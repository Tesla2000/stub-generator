import subprocess
from pathlib import Path
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class Black(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["black"] = "black"

    def process(self, pyi_paths: list[Path]) -> None:
        """Run black --quiet on the given stub files in-place."""
        subprocess.run(
            ["black", "--quiet"] + list(map(str, pyi_paths)),
            check=True,
        )
