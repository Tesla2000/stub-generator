import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import tomli
import tomlkit
from pydantic import BaseModel, Field, HttpUrl
from pydantic_logger import PydanticLogger
from ts_utils.metadata import get_recursive_requirements, read_metadata
from ts_utils.utils import get_mypy_req

from stub_adder._stub_tuple import _StubTuple
from stub_adder.input._version_service import VersionService
from stub_adder.input.version_extractor import (
    GithubReleaseExtractor,
    InstalledPackageExtractor,
    PipPackageVersionExtractor,
    PyprojectTomlExtractor,
    SetupCfgExtractor,
    SetupPyExtractor,
)


def _default_version_service(data: dict[str, object]) -> VersionService:
    url = data.get("stubbed_repo_url")
    path = data.get("stubbed_path")
    if url is None or path is None:
        raise ValueError(
            "stubbed_repo_url and path is required to build the default VersionService"
        )
    assert isinstance(path, Path)
    repo_name = urlparse(str(url)).path.strip("/").removesuffix(".git")
    return VersionService(
        extractors=(
            PipPackageVersionExtractor(package_name=path.name),
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
    stubbed_path: Path
    venv_path: Path = Field(
        default_factory=lambda: Path(tempfile.TemporaryDirectory().name)
    )
    version_service: VersionService = Field(
        default_factory=_default_version_service
    )

    def ensure_cloned(self, stubs_dir: Path) -> Path:
        """Create a venv at clone_path with the package installed.

        Delegates directly to ``setup_stubtest_venv`` — the same function
        ``run_stubtest`` uses internally — so both the stub-generation venv and
        the stubtest venv track the same revision from METADATA.toml.

        *stubs_dir* must contain a valid METADATA.toml.  ``generate()`` always
        writes one before calling this method; ``Stubtest.generate()`` calls it
        only after stubs already exist.
        """
        if (self.venv_path / "pyvenv.cfg").exists():
            self.logger.debug(f"Venv already exists at {self.venv_path}")
            return self.venv_path

        self.setup_stubtest_venv(stubs_dir, venv_dir=self.venv_path)
        self.logger.debug(f"Venv ready at {self.venv_path}")
        return self.venv_path

    def generate(self, output_path: Path) -> Iterable[_StubTuple]:
        # Write METADATA.toml before ensure_cloned so setup_stubtest_venv can
        # read metadata.version_spec from it.
        metadata_toml = output_path / "METADATA.toml"
        if not metadata_toml.exists():
            version = self.version_service.get_version(Path())
            output_path.mkdir(parents=True, exist_ok=True)
            doc = tomlkit.document()
            doc["version"] = version
            doc["upstream-repository"] = str(self.stubbed_repo_url)
            metadata_toml.write_text(tomlkit.dumps(doc))

        self.ensure_cloned(output_path)

        site_packages = self._site_packages()

        self.logger.debug("Generating stub files...")
        package_path = output_path / self.stubbed_path
        self._generate_stubs([site_packages / self.stubbed_path], package_path)
        init_path = package_path.joinpath("__init__.pyi")
        if not init_path.exists():
            init_path.write_text("")
        self.logger.debug("Stub generation complete!")
        yield from (
            _StubTuple(
                py_path=original_path.absolute(),
                pyi_path=output_path.joinpath(
                    original_path.relative_to(site_packages).with_suffix(
                        ".pyi"
                    )
                ).absolute(),
            )
            for original_path in (site_packages / self.stubbed_path).rglob(
                "*.py"
            )
        )

    def _site_packages(self) -> Path:
        if sys.platform == "win32":
            return self.venv_path / "Lib" / "site-packages"
        return next((self.venv_path / "lib").glob("python*/site-packages"))

    @staticmethod
    def _extract_package_name(repo_path: Path) -> Path:
        pyproject_toml = repo_path / "pyproject.toml"
        if pyproject_toml.exists():
            data = tomli.loads(pyproject_toml.read_text())
            if "project" in data and "name" in data["project"]:
                return Path(data["project"]["name"])
        return repo_path

    @staticmethod
    def _generate_stubs(paths: Iterable[Path], output_dir: Path) -> None:
        for path in paths:
            if output_dir.exists() and any(output_dir.rglob("*.pyi")):
                continue
            subprocess.run(
                ["stubgen", str(path), "-o", str(output_dir)],
                capture_output=True,
                text=True,
                check=True,
            )

    def _print_command_output(
        self,
        e: subprocess.CalledProcessError | subprocess.CompletedProcess[bytes],
    ) -> None:
        self.logger.debug(e.stdout.decode() + e.stderr.decode())

    def _raise_command_failure(
        self, message: str, e: subprocess.CalledProcessError
    ) -> None:
        raise ValueError(message, e.stdout, e.stderr)

    def setup_stubtest_venv(self, dist: Path, venv_dir: Path) -> bool:
        """Create a venv at *venv_dir* and install the distribution's stubtest dependencies.

        Uses the same package versions that ``run_stubtest`` would install, so a
        venv prepared here can be reused by ``run_stubtest_in_venv``.
        """
        dist = dist.resolve()
        dist_name = dist.name
        old_cwd = os.getcwd()
        try:
            os.chdir(dist.parent.parent)
            metadata = read_metadata(dist_name)
            requirements = get_recursive_requirements(dist_name)
        finally:
            os.chdir(old_cwd)
        stubtest_settings = metadata.stubtest_settings

        try:
            subprocess.run(
                ["uv", "venv", str(venv_dir), "--seed"],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            self._raise_command_failure(
                "Failed to create a virtualenv (likely a bug in uv?)", e
            )

        if sys.platform == "win32":
            pip_exe = str(venv_dir / "Scripts" / "pip.exe")
        else:
            pip_exe = str(venv_dir / "bin" / "pip")

        dist_extras = ", ".join(stubtest_settings.extras)
        dist_req = f"{dist_name}[{dist_extras}]{metadata.version_spec}"

        # We need stubtest to be able to import the package, so install mypy into the venv
        # Hopefully mypy continues to not need too many dependencies
        dists_to_install = [dist_req, get_mypy_req()]
        # Internal requirements are added to MYPYPATH
        dists_to_install.extend(str(r) for r in requirements.external_pkgs)
        dists_to_install.extend(stubtest_settings.stubtest_dependencies)

        # Since the "gdb" Python package is available only inside GDB, it is not
        # possible to install it through pip, so stub tests cannot install it.
        if dist_name == "gdb":
            dists_to_install[:] = dists_to_install[1:]

        pip_cmd = [pip_exe, "install", "--no-cache-dir", *dists_to_install]
        try:
            subprocess.run(pip_cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            self._raise_command_failure("Failed to install", e)

        return True
