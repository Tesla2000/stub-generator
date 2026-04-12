import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

import tomli
from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple


class StubGenerator(BaseModel):
    logger: PydanticLogger = Field(
        default_factory=lambda: PydanticLogger(name=__name__)
    )
    stubbed_repo_url: HttpUrl
    paths: list[Path]
    clone_path: Path = Field(
        default_factory=lambda: Path(tempfile.TemporaryDirectory().name)
    )

    def generate(self, output_path: Path) -> Iterable[_StubTuple]:
        self.logger.debug(
            f"Cloning repository from {self.stubbed_repo_url}..."
        )

        # Clone the repository
        subprocess.run(
            ["git", "clone", str(self.stubbed_repo_url), str(self.clone_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        self.logger.debug(f"Repository cloned to {self.clone_path}")

        package_paths = tuple(map(self.clone_path.joinpath, self.paths))

        self.logger.debug("Generating stub files...")
        self._generate_stubs(
            package_paths,
            output_path,
        )

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
            out = output_dir / path.name
            if out.exists() and any(out.rglob("*.pyi")):
                continue
            subprocess.run(
                [
                    "stubgen",
                    str(path),
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
