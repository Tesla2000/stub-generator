import json
import os
import subprocess
from pathlib import Path
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class Pyright(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["pyright"] = "pyright"

    @staticmethod
    def generate(
        pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run pyright and return per-file error lines for files with errors."""
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(stubs_dir)
            if not existing
            else f"{stubs_dir}{os.pathsep}{existing}"
        )
        result = subprocess.run(
            ["pyright", "--outputjson"] + list(map(str, pyi_paths)),
            capture_output=True,
            text=True,
            env=env,
        )
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        diagnostics = data.get("generalDiagnostics", [])
        errors: dict[Path, list[str]] = {}
        for diag in diagnostics:
            if diag.get("severity") == "error":
                file_path = Path(diag["file"])
                if file_path in pyi_paths:
                    line = (
                        diag.get("range", {}).get("start", {}).get("line", 0)
                        + 1
                    )
                    message = diag.get("message", "")
                    errors.setdefault(file_path, []).append(
                        f"{file_path}:{line}: error: {message}"
                    )
        return errors
