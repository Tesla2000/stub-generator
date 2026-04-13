import configparser
from pathlib import Path
from typing import Literal

from stub_adder.input.version_extractor._base import VersionExtractorBase


class SetupCfgExtractor(VersionExtractorBase):
    type: Literal["setup_cfg"] = "setup_cfg"

    def __call__(self, repo_path: Path) -> str | None:
        setup_cfg = repo_path / "setup.cfg"
        if not setup_cfg.exists():
            return None
        cfg = configparser.ConfigParser()
        cfg.read(setup_cfg)
        version = cfg.get("metadata", "version", fallback=None)
        if version and not version.startswith(("attr:", "file:")):
            return version
        return None
