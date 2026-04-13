from pathlib import Path
from typing import Literal

import tomli

from stub_adder.input.version_extractor._base import VersionExtractorBase


class PyprojectTomlExtractor(VersionExtractorBase):
    type: Literal["pyproject_toml"] = "pyproject_toml"

    def __call__(self, repo_path: Path) -> str | None:
        pyproject = repo_path / "pyproject.toml"
        if not pyproject.exists():
            return None
        data = tomli.loads(pyproject.read_text())
        version: object = data.get("project", {}).get("version") or data.get(
            "tool", {}
        ).get("poetry", {}).get("version")
        return version if isinstance(version, str) and version else None
