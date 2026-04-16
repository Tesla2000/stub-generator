from pathlib import Path

from pydantic import BaseModel, ConfigDict

from stub_adder.input.version_extractor import AnyVersionExtractor


def _format_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) >= 3:
        return version
    return version + ".*"


class VersionService(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    extractors: tuple[AnyVersionExtractor, ...]

    def get_version(self, repo_path: Path) -> str:
        for extractor in self.extractors:
            version = extractor(repo_path)
            if version:
                return _format_version(version)
        raise ValueError("Version couldn't be extracted")
