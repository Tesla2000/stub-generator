import subprocess
from pathlib import Path
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class Flake8(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["flake8"] = "flake8"

    @staticmethod
    def generate(
        pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run flake8 with flake8-pyi and return per-file error lines."""
        pyi_paths = [p.resolve() for p in pyi_paths]
        result = subprocess.run(
            [
                "flake8",
                "--extend-select=Y",
            ]
            + list(map(str, pyi_paths)),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {}
        errors: dict[Path, list[str]] = {}
        for line in result.stdout.splitlines():
            # format: /abs/path/file.pyi:line:col: CODE message
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            file_path = Path(parts[0])
            if file_path in pyi_paths:
                errors.setdefault(file_path, []).append(line)
        return errors
