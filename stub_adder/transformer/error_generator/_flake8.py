import subprocess
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase


class Flake8Config(BaseModel):
    """flake8 configuration mirroring typeshed's .flake8 defaults."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    # Only run flake8-pyi (Y) rules — matches typeshed's "select = Y"
    select: tuple[str, ...] = ("Y",)
    # Matches typeshed's "extend-ignore = Y090,Y091"
    extend_ignore: tuple[str, ...] = ("Y090", "Y091")


class Flake8(ErrorGeneratorBase):
    type: Literal["flake8"] = "flake8"
    config: Flake8Config = Flake8Config()

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run flake8 with flake8-pyi and return per-file error lines."""
        pyi_paths = [p.resolve() for p in pyi_paths]
        cmd = [
            "flake8",
            f"--select={','.join(self.config.select)}",
            f"--extend-ignore={','.join(self.config.extend_ignore)}",
        ]
        result = subprocess.run(
            cmd + list(map(str, pyi_paths)),
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
