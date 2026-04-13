import re
from pathlib import Path
from typing import Literal

from stub_adder.input.version_extractor._base import VersionExtractorBase


class SetupPyExtractor(VersionExtractorBase):
    type: Literal["setup_py"] = "setup_py"

    def __call__(self, repo_path: Path) -> str | None:
        setup_py = repo_path / "setup.py"
        if not setup_py.exists():
            return None
        match = re.search(
            r"""version\s*=\s*['"]([^'"]+)['"]""",
            setup_py.read_text(),
        )
        return match.group(1) if match else None
