from enum import auto
from enum import StrEnum


class VersionExtractorType(StrEnum):
    GITHUB_RELEASE = auto()
    PYPROJECT_TOML = auto()
    SETUP_CFG = auto()
    SETUP_PY = auto()
    INSTALLED_PACKAGE = auto()
