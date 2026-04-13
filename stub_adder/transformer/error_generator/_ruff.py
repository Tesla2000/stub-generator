import json
import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase


class Ruff(ErrorGeneratorBase):
    type: Literal["ruff"] = "ruff"
    select: tuple[str, ...] = ("FA", "I", "ICN001", "RUF100")
    unsafe_fixes: bool = False

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run ruff check and return per-file error lines."""
        pyi_paths = [p.resolve() for p in pyi_paths]
        cmd = [
            "ruff",
            "check",
            "--output-format=json",
            "--exit-non-zero-on-fix",
            f"--select={','.join(self.select)}",
        ]
        if self.unsafe_fixes:
            cmd.append("--unsafe-fixes")
        cmd += list(map(str, pyi_paths))
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            diagnostics = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        errors: dict[Path, list[str]] = {}
        for diag in diagnostics:
            file_path = Path(diag["filename"]).resolve()
            if file_path in pyi_paths:
                row = diag["location"]["row"]
                code = diag["code"]
                message = diag["message"]
                errors.setdefault(file_path, []).append(
                    f"{file_path}:{row}: error: {code} {message}"
                )
        return errors
