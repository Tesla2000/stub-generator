import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class RuffIsort(ProcessBase):
    type: Literal["ruff_isort"] = "ruff_isort"

    def process(self, pyi_paths: list[Path]) -> None:
        """Run ruff --fix --select I to sort imports in-place."""
        subprocess.run(
            ("ruff", "check", "--fix", "--select", "I")
            + tuple(map(str, pyi_paths)),
            capture_output=True,
        )
