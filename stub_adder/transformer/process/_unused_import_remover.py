import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class UnusedImportRemover(ProcessBase):
    type: Literal["unused_import_remover"] = "unused_import_remover"

    def process(self, pyi_paths: list[Path]) -> None:
        subprocess.run(
            ("ruff", "check", "--fix", "--select", "F401")
            + tuple(map(str, pyi_paths)),
            capture_output=True,
        )
