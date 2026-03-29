import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

import tomli
from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic_logger import PydanticLogger


class StubGenerator(BaseModel):
    logger: PydanticLogger = Field(
        default_factory=lambda: PydanticLogger(name=__name__)
    )
    paths: Optional[list[Path]] = None

    def generate(self, stubbed_repo_url: HttpUrl, typeshed_path: Path) -> None:
        # Create a temporary directory for cloning
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "repo"

            self.logger.debug(f"Cloning repository from {stubbed_repo_url}...")

            # Clone the repository
            subprocess.run(
                ["git", "clone", str(stubbed_repo_url), str(repo_path)],
                capture_output=True,
                text=True,
                check=True,
            )

            self.logger.debug(f"Repository cloned to {repo_path}")

            package_paths: tuple[Path, ...]
            if self.paths is None:
                package_paths = (
                    repo_path / self._extract_package_name(repo_path),
                )
                self.logger.debug(f"Detected package name: {package_paths}")
            else:
                package_paths = tuple(map(repo_path.joinpath, self.paths))

            self.logger.debug("Generating stub files...")
            self._generate_stubs(
                package_paths,
                typeshed_path / "stubs" / str(stubbed_repo_url).split("/")[-1],
            )

            self.logger.debug("Stub generation complete!")

    @staticmethod
    def _extract_package_name(repo_path: Path) -> Path:
        # Try to find setup.py or pyproject.toml
        pyproject_toml = repo_path / "pyproject.toml"

        if pyproject_toml.exists():
            data = tomli.loads(pyproject_toml.read_text())
            if "project" in data and "name" in data["project"]:
                return Path(data["project"]["name"])

        # Last resort: use the repo directory name
        return repo_path

    @classmethod
    def _generate_stubs(cls, paths: Iterable[Path], output_dir: Path) -> None:
        for path in paths:
            subprocess.run(
                [
                    "stubgen",
                    str(path),
                    "-o",
                    str(output_dir / path.name),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
