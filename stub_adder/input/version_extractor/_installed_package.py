import importlib.metadata
from pathlib import Path
from typing import Literal

from stub_adder.input.version_extractor._base import VersionExtractorBase


class InstalledPackageExtractor(VersionExtractorBase):
    type: Literal["installed_package"] = "installed_package"

    def __call__(self, repo_path: Path) -> str | None:
        # EAFP: package may not be installed
        try:
            return importlib.metadata.version(repo_path.name)
        except importlib.metadata.PackageNotFoundError:
            return None
