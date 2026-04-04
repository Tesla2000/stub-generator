import subprocess
from pathlib import Path


def run_mypy(pyi_paths: list[Path]) -> dict[Path, list[str]]:
    """Run mypy --strict and return per-file error lines for files with errors."""
    result = subprocess.run(
        ["mypy", "--strict"] + list(map(str, pyi_paths)),
        capture_output=True,
        text=True,
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
