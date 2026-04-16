from typing import Union

from stub_adder.input.version_extractor._base import VersionExtractorBase
from stub_adder.input.version_extractor._github_release import (
    GithubReleaseExtractor,
)
from stub_adder.input.version_extractor._pip_package_version import (
    PipPackageVersionExtractor,
)

AnyVersionExtractor = Union[
    GithubReleaseExtractor,
    PipPackageVersionExtractor,
]

__all__: list[str] = [
    "VersionExtractorBase",
    "GithubReleaseExtractor",
    "PipPackageVersionExtractor",
    "AnyVersionExtractor",
]
