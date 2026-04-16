from enum import StrEnum, auto


class VersionExtractorType(StrEnum):
    GITHUB_RELEASE = auto()
    PYPROJECT_TOML = auto()
    SETUP_CFG = auto()
    SETUP_PY = auto()
    INSTALLED_PACKAGE = auto()
