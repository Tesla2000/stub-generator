import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar
from typing import Literal

from mypy.nodes import defaultdict
from pydantic import BaseModel
from pydantic import ConfigDict
from ts_utils.metadata import get_recursive_requirements
from ts_utils.metadata import read_metadata
from ts_utils.mypy import mypy_configuration_from_distribution
from ts_utils.mypy import temporary_mypy_config_file
from ts_utils.utils import allowlist_stubtest_arguments
from ts_utils.utils import get_mypy_req

# Cache: dist_name -> venv python exe path
_VENV_CACHE: dict[str, Path] = {}


class Stubtest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["stubtest"] = "stubtest"
    ci_platforms_only: bool = True
    _ERROR_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^error: (\S+)", re.MULTILINE
    )

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        """Run stubtest and return per-file errors.

        Creates a venv on first call and caches it.  Subsequent calls
        reuse the cached venv.  Only checks modules corresponding to
        the given *pyi_paths* (the current layer).
        """
        stubs_dir = stubs_dir.resolve()
        dist_name = stubs_dir.name
        typeshed_dir = stubs_dir.parent.parent

        python_exe = self._get_or_create_venv(dist_name, typeshed_dir)

        # Derive module names from the layer's pyi files.
        modules = self._pyi_paths_to_modules(pyi_paths, stubs_dir)
        if not modules:
            raise ValueError("Modules not defined")

        output = self._run_stubtest(
            python_exe, modules, dist_name, stubs_dir, typeshed_dir
        )
        if output is None:
            return {}

        pyi_set = {p.resolve() for p in pyi_paths}
        all_errors = self._parse_errors(output, stubs_dir)
        return {p: e for p, e in all_errors.items() if p in pyi_set}

    @staticmethod
    def _get_or_create_venv(dist_name: str, typeshed_dir: Path) -> Path:
        """Return the cached venv python path, creating it if needed."""
        if dist_name in _VENV_CACHE and _VENV_CACHE[dist_name].exists():
            return _VENV_CACHE[dist_name]

        old_cwd = os.getcwd()
        try:
            os.chdir(typeshed_dir)
            metadata = read_metadata(dist_name)
        finally:
            os.chdir(old_cwd)

        stubtest_settings = metadata.stubtest_settings
        venv_dir = Path(tempfile.mkdtemp(prefix="stubtest-"))
        subprocess.run(
            ["uv", "venv", str(venv_dir), "--seed"],
            capture_output=True,
            check=True,
        )

        pip_exe = venv_dir / "bin" / "pip"
        python_exe = venv_dir / "bin" / "python"

        dist_extras = ", ".join(stubtest_settings.extras)
        dist_req = f"{dist_name}[{dist_extras}]{metadata.version_spec}"

        old_cwd = os.getcwd()
        try:
            os.chdir(typeshed_dir)
            requirements = get_recursive_requirements(dist_name)
        finally:
            os.chdir(old_cwd)

        dists_to_install = [dist_req, get_mypy_req()]
        dists_to_install.extend(str(r) for r in requirements.external_pkgs)
        dists_to_install.extend(stubtest_settings.stubtest_dependencies)

        subprocess.run(
            [str(pip_exe), "install", *dists_to_install],
            check=True,
            capture_output=True,
        )
        _VENV_CACHE[dist_name] = python_exe
        return python_exe

    def _run_stubtest(
        self,
        python_exe: Path,
        modules: list[str],
        dist_name: str,
        stubs_dir: Path,
        typeshed_dir: Path,
    ) -> str | None:
        """Run mypy.stubtest for specific modules."""
        old_cwd = os.getcwd()
        try:
            os.chdir(typeshed_dir)
            mypy_configuration = mypy_configuration_from_distribution(
                dist_name
            )
            metadata = read_metadata(dist_name)
            stubtest_settings = metadata.stubtest_settings
            requirements = get_recursive_requirements(dist_name)
        finally:
            os.chdir(old_cwd)

        with temporary_mypy_config_file(
            mypy_configuration, stubtest_settings
        ) as temp:
            ignore_missing_stub = (
                ["--ignore-missing-stub"]
                if stubtest_settings.ignore_missing_stub
                else []
            )
            cmd = [
                str(python_exe),
                "-m",
                "mypy.stubtest",
                "--mypy-config-file",
                temp.name,
                "--show-traceback",
                "--strict-type-check-only",
                "--custom-typeshed-dir",
                str(typeshed_dir),
                *ignore_missing_stub,
                *modules,
                *allowlist_stubtest_arguments(dist_name),
            ]
            mypypath_items = [str(stubs_dir)] + [
                str(stubs_dir.parent / pkg.name)
                for pkg in requirements.typeshed_pkgs
            ]
            env = os.environ | {
                "MYPYPATH": os.pathsep.join(mypypath_items),
                "PYTHONUTF8": "1",
            }
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env
            )

        if result.returncode == 0:
            return None
        return result.stdout + result.stderr

    @staticmethod
    def _pyi_paths_to_modules(
        pyi_paths: list[Path], stubs_dir: Path
    ) -> list[str]:
        """Convert .pyi file paths to dotted module names for stubtest."""
        modules: set[str] = set()
        for pyi in pyi_paths:
            try:
                rel = pyi.resolve().relative_to(stubs_dir)
            except ValueError:
                continue
            parts = list(rel.parts)
            # Remove .pyi suffix from last part
            if parts[-1].endswith(".pyi"):
                parts[-1] = parts[-1][:-4]
            # __init__ → package name (drop __init__)
            if parts[-1] == "__init__":
                parts.pop()
            if parts:
                modules.add(parts[0])
        return sorted(modules)

    def _parse_errors(
        self, output: str, stubs_dir: Path
    ) -> dict[Path, list[str]]:
        errors: dict[Path, list[str]] = defaultdict(list)
        blocks = re.split(r"(?=^error: )", output, flags=re.MULTILINE)
        for block in blocks:
            block = block.strip()
            if not block.startswith("error:"):
                continue
            m = self._ERROR_RE.match(block)
            if not m:
                continue
            dotted = m.group(1)
            pyi = self._resolve_pyi(dotted, stubs_dir)
            if pyi is not None:
                errors[pyi].append(block)
        return errors

    @staticmethod
    def _resolve_pyi(dotted: str, stubs_dir: Path) -> Path | None:
        """Map a dotted module path to the corresponding .pyi file."""
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            candidate = stubs_dir / "/".join(parts[:i])
            init = candidate / "__init__.pyi"
            if init.exists():
                return init.resolve()
            module = candidate.with_suffix(".pyi")
            if module.exists():
                return module.resolve()
        return None
