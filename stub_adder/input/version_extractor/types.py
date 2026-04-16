from enum import StrEnum, auto


class VersionExtractorType(StrEnum):
    GITHUB_RELEASE = auto()
    PIP_PACKAGE_VERSION = auto()
