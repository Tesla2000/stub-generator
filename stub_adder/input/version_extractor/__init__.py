from typing import Union

from stub_adder.input.version_extractor._base import VersionExtractorBase
from stub_adder.input.version_extractor._github_release import (
    GithubReleaseExtractor,
)
from stub_adder.input.version_extractor._installed_package import (
    InstalledPackageExtractor,
)
from stub_adder.input.version_extractor._pyproject_toml import (
    PyprojectTomlExtractor,
)
from stub_adder.input.version_extractor._setup_cfg import SetupCfgExtractor
from stub_adder.input.version_extractor._setup_py import SetupPyExtractor

AnyVersionExtractor = Union[
    GithubReleaseExtractor,
    PyprojectTomlExtractor,
    SetupCfgExtractor,
    SetupPyExtractor,
    InstalledPackageExtractor,
]

__all__: list[str] = [
    "VersionExtractorBase",
    "GithubReleaseExtractor",
    "PyprojectTomlExtractor",
    "SetupCfgExtractor",
    "SetupPyExtractor",
    "InstalledPackageExtractor",
    "AnyVersionExtractor",
]
