import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class Pyupgrade(ProcessBase):
    type: Literal["pyupgrade"] = "pyupgrade"
    min_version: tuple[int, int] = (3, 10)

    def process(self, pyi_paths: list[Path]) -> None:
        """Run pyupgrade on the given stub files in-place."""
        version_flag = f"--py{''.join(map(str, self.min_version))}-plus"
        subprocess.run(
            ["pyupgrade", version_flag] + list(map(str, pyi_paths)),
        )
