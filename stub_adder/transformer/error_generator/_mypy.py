import os
import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase


class Mypy(ErrorGeneratorBase):
    type: Literal["mypy"] = "mypy"

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run mypy --strict and return per-file error lines for files with errors."""
        env = os.environ.copy()
        existing = env.get("MYPYPATH", "")
        env["MYPYPATH"] = (
            str(stubs_dir)
            if not existing
            else f"{stubs_dir}{os.pathsep}{existing}"
        )
        result = subprocess.run(
            ["mypy", "--strict"] + list(map(str, pyi_paths)),
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode == 0:
            return {}
        return {
            pyi: lines
            for pyi in pyi_paths
            if (
                lines := [
                    line
                    for line in result.stdout.splitlines()
                    if line.startswith(str(pyi) + ":")
                ]
            )
        }
