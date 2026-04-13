import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import tomli
import tomlkit
from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple
from stub_adder.input._version_service import VersionService
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


def _default_version_service(data: dict[str, object]) -> VersionService:
    url = data.get("stubbed_repo_url")
    if url is None:
        raise ValueError(
            "stubbed_repo_url is required to build the default VersionService"
        )
    repo_name = urlparse(str(url)).path.strip("/")
    return VersionService(
        extractors=(
            GithubReleaseExtractor(repo_name=repo_name),
            PyprojectTomlExtractor(),
            SetupCfgExtractor(),
            SetupPyExtractor(),
            InstalledPackageExtractor(),
        )
    )


class StubGenerator(BaseModel):
    logger: PydanticLogger = PydanticLogger(name=__name__)
    stubbed_repo_url: HttpUrl
    paths: list[Path]
    clone_path: Path = Field(
        default_factory=lambda: Path(tempfile.TemporaryDirectory().name)
    )
    version_service: VersionService = Field(
        default_factory=_default_version_service
    )

    def generate(self, output_path: Path) -> Iterable[_StubTuple]:
        self.logger.debug(
            f"Cloning repository from {self.stubbed_repo_url}..."
        )

        subprocess.run(
            ["git", "clone", str(self.stubbed_repo_url), str(self.clone_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        self.logger.debug(f"Repository cloned to {self.clone_path}")

        metadata_toml = output_path / "METADATA.toml"
        if not metadata_toml.exists():
            version = self.version_service.get_version(self.clone_path)
            output_path.mkdir(parents=True, exist_ok=True)
            doc = tomlkit.document()
            doc["version"] = version
            doc["upstream-repository"] = str(self.stubbed_repo_url)
            metadata_toml.write_text(tomlkit.dumps(doc))

        package_paths = tuple(map(self.clone_path.joinpath, self.paths))

        self.logger.debug("Generating stub files...")
        self._generate_stubs(package_paths, output_path)

        self.logger.debug("Stub generation complete!")
        yield from (
            _StubTuple(
                py_path=original_path.absolute(),
                pyi_path=output_path.joinpath(
                    original_path.relative_to(self.clone_path).with_suffix(
                        ".pyi"
                    )
                ).absolute(),
            )
            for path in package_paths
            for original_path in path.rglob("*.py")
        )

    @staticmethod
    def _extract_package_name(repo_path: Path) -> Path:
        pyproject_toml = repo_path / "pyproject.toml"
        if pyproject_toml.exists():
            data = tomli.loads(pyproject_toml.read_text())
            if "project" in data and "name" in data["project"]:
                return Path(data["project"]["name"])
        return repo_path

    @classmethod
    def _generate_stubs(cls, paths: Iterable[Path], output_dir: Path) -> None:
        for path in paths:
            if output_dir.exists() and any(output_dir.rglob("*.pyi")):
                continue
            subprocess.run(
                ["stubgen", str(path), "-o", str(output_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
