import re
import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.input.version_extractor._base import VersionExtractorBase
from stub_adder.input.version_extractor.types import VersionExtractorType

_VERSION_RE = re.compile(r"\(([^)]+)\)")


class PipPackageVersionExtractor(VersionExtractorBase):
    type: Literal[VersionExtractorType.PIP_PACKAGE_VERSION] = (
        VersionExtractorType.PIP_PACKAGE_VERSION
    )
    package_name: str

    def __call__(self, repo_path: Path) -> str | None:
        result = subprocess.run(
            ["pip", "index", "versions", self.package_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            m = _VERSION_RE.search(line)
            if m:
                return m.group(1)
        return None
