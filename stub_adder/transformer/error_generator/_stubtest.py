import contextlib
import io
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from time import time
from typing import ClassVar, Literal

from pydantic_logger import PydanticLogger
from ts_utils.metadata import get_recursive_requirements, read_metadata
from ts_utils.mypy import (
    mypy_configuration_from_distribution,
    temporary_mypy_config_file,
)
from ts_utils.paths import allowlists_path
from ts_utils.utils import (
    PYTHON_VERSION,
    allowlist_stubtest_arguments,
    get_mypy_req,
    print_divider,
    print_error,
    print_info,
    print_success_msg,
    print_time,
    print_warning,
)

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase
from typeshed.tests.stubtest_third_party import (
    run_stubtest,
    setup_gdb_stubtest_command,
    setup_uwsgi_stubtest_command,
)

_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")


class Stubtest(ErrorGeneratorBase):
    type: Literal["stubtest"] = "stubtest"
    ci_platforms_only: bool = True
    venv_path: Path | None = None
    _ERROR_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^error: (\S+)", re.MULTILINE
    )
    logger: PydanticLogger = PydanticLogger(name=__name__)

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        stubs_dir = stubs_dir.resolve()
        typeshed_dir = stubs_dir.parent.parent
        venv_path = (
            self.venv_path.resolve() if self.venv_path is not None else None
        )

        buffer = io.StringIO()
        old_cwd = os.getcwd()
        try:
            os.chdir(typeshed_dir)
            with contextlib.redirect_stdout(buffer):
                if venv_path is not None:
                    success = self.run_stubtest_in_venv(
                        stubs_dir,
                        venv_path,
                        ci_platforms_only=self.ci_platforms_only,
                        keep_tmp_dir=True,
                    )
                else:
                    success = run_stubtest(
                        stubs_dir,
                        ci_platforms_only=self.ci_platforms_only,
                    )
        finally:
            os.chdir(old_cwd)

        if success:
            return {}

        pyi_set = {p.resolve() for p in pyi_paths}
        all_errors = self._parse_errors(buffer.getvalue(), stubs_dir)
        return {p: e for p, e in all_errors.items() if p in pyi_set}

    def _parse_errors(
        self, output: str, stubs_dir: Path
    ) -> dict[Path, list[str]]:
        output = _ANSI_RE.sub("", output)
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

    def _print_commands(
        self, pip_cmd: list[str], stubtest_cmd: list[str], mypypath: str
    ) -> None:
        self.logger.debug(" ".join(pip_cmd))
        self.logger.debug(f"MYPYPATH={mypypath} " + " ".join(stubtest_cmd))

    def _print_command_output(
        self,
        e: subprocess.CalledProcessError | subprocess.CompletedProcess[bytes],
    ) -> None:
        self.logger.debug(e.stdout.decode() + e.stderr.decode())

    def run_stubtest_in_venv(
        self,
        dist: Path,
        venv_dir: Path,
        *,
        verbose: bool = False,
        ci_platforms_only: bool = False,
        keep_tmp_dir: bool = False,
    ) -> bool:
        """Run stubtest for *dist* using an existing venv at *venv_dir*.

        Performs the same skip checks and produces the same output as
        ``run_stubtest``, but skips venv creation/teardown so a venv prepared by
        ``setup_stubtest_venv`` (or reused across calls) can be passed in.
        """
        dist_name = dist.name
        metadata = read_metadata(dist_name)

        t = time()

        stubtest_settings = metadata.stubtest_settings
        if stubtest_settings.skip:
            self.logger.debug("skipping (skip = true)")
            return True

        if (
            stubtest_settings.supported_platforms is not None
            and sys.platform not in stubtest_settings.supported_platforms
        ):
            self.logger.debug("skipping (platform not supported)")
            return True

        if (
            ci_platforms_only
            and sys.platform not in stubtest_settings.ci_platforms
        ):
            self.logger.debug("skipping (platform skipped in CI)", "yellow")
            return True

        if not metadata.requires_python.contains(PYTHON_VERSION):
            self.logger.debug(
                f"skipping (requires Python {metadata.requires_python})"
            )
            return True

        if sys.platform == "win32":
            pip_exe = str(venv_dir / "Scripts" / "pip.exe")
            python_exe = str(venv_dir / "Scripts" / "python.exe")
        else:
            pip_exe = str(venv_dir / "bin" / "pip")
            python_exe = str(venv_dir / "bin" / "python")

        requirements = get_recursive_requirements(dist_name)
        dist_extras = ", ".join(stubtest_settings.extras)
        dist_req = f"{dist_name}[{dist_extras}]{metadata.version_spec}"
        dists_to_install = [dist_req, get_mypy_req()]
        dists_to_install.extend(str(r) for r in requirements.external_pkgs)
        dists_to_install.extend(stubtest_settings.stubtest_dependencies)
        pip_cmd = [pip_exe, "install", *dists_to_install]

        mypy_configuration = mypy_configuration_from_distribution(dist_name)
        with temporary_mypy_config_file(
            mypy_configuration, stubtest_settings
        ) as temp:
            ignore_missing_stub = (
                ["--ignore-missing-stub"]
                if stubtest_settings.ignore_missing_stub
                else []
            )
            packages_to_check = [
                d.name
                for d in dist.iterdir()
                if d.is_dir() and d.name.isidentifier()
            ]
            modules_to_check = [
                d.stem
                for d in dist.iterdir()
                if d.is_file() and d.suffix == ".pyi"
            ]
            stubtest_cmd = [
                python_exe,
                "-m",
                "mypy.stubtest",
                "--mypy-config-file",
                temp.name,
                "--show-traceback",
                "--strict-type-check-only",
                # Use --custom-typeshed-dir in case we make linked changes to stdlib or _typeshed
                "--custom-typeshed-dir",
                str(dist.parent.parent),
                *ignore_missing_stub,
                *packages_to_check,
                *modules_to_check,
                *allowlist_stubtest_arguments(dist_name),
            ]

            stubs_dir = dist.parent
            mypypath_items = [str(dist)] + [
                str(stubs_dir / pkg.name) for pkg in requirements.typeshed_pkgs
            ]
            mypypath = os.pathsep.join(mypypath_items)
            # For packages that need a display, we need to pass at least $DISPLAY
            # to stubtest. $DISPLAY is set by xvfb-run in CI.
            #
            # It seems that some other environment variables are needed too,
            # because the CI fails if we pass only os.environ["DISPLAY"]. I didn't
            # "bisect" to see which variables are actually needed.
            stubtest_env = os.environ | {
                "MYPYPATH": mypypath,
                "MYPY_FORCE_COLOR": "1",
                # Prevent stubtest crash due to special unicode character
                # https://github.com/python/mypy/issues/19071
                "PYTHONUTF8": "1",
            }

            # Perform some black magic in order to run stubtest inside uWSGI
            if dist_name == "uWSGI":
                if not setup_uwsgi_stubtest_command(
                    dist, venv_dir, stubtest_cmd
                ):
                    return False

            if dist_name == "gdb":
                if not setup_gdb_stubtest_command(venv_dir, stubtest_cmd):
                    return False

            try:
                subprocess.run(
                    stubtest_cmd,
                    env=stubtest_env,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                print_time(time() - t)
                print_error("fail")

                print_divider()
                self.logger.debug("Commands run:")
                self._print_commands(pip_cmd, stubtest_cmd, mypypath)

                print_divider()
                self.logger.debug("Command output:\n")
                self._print_command_output(e)

                print_divider()
                self.logger.debug("Python version: ")
                ret = subprocess.run(
                    [sys.executable, "-VV"], capture_output=True, check=False
                )
                self._print_command_output(ret)

                self.logger.debug("\nRan with the following environment:")
                ret = subprocess.run(
                    [pip_exe, "freeze", "--all"],
                    capture_output=True,
                    check=False,
                )
                self._print_command_output(ret)
                if keep_tmp_dir:
                    self.logger.debug(
                        f"Path to virtual environment: {venv_dir}"
                    )

                print_divider()
                main_allowlist_path = (
                    allowlists_path(dist_name) / "stubtest_allowlist.txt"
                )
                if main_allowlist_path.exists():
                    self.logger.debug(
                        f'To fix "unused allowlist" errors, remove the corresponding entries from {main_allowlist_path}'
                    )
                else:
                    self.logger.debug(
                        f"Re-running stubtest with --generate-allowlist.\nAdd the following to {main_allowlist_path}:"
                    )
                    ret = subprocess.run(
                        [*stubtest_cmd, "--generate-allowlist"],
                        env=stubtest_env,
                        capture_output=True,
                        check=False,
                    )
                    self._print_command_output(ret)

                print_divider()
                self.logger.debug(
                    f"Upstream repository: {metadata.upstream_repository}"
                )
                self.logger.debug(
                    f"Typeshed source code: https://github.com/python/typeshed/tree/main/stubs/{dist.name}"
                )

                print_divider()

                return False
            else:
                print_time(time() - t)
                print_success_msg()

                if sys.platform not in stubtest_settings.ci_platforms:
                    print_warning(
                        f"Note: {dist_name} is not currently tested on {sys.platform} in typeshed's CI"
                    )

                if keep_tmp_dir:
                    print_info(f"Virtual environment kept at: {venv_dir}")

        if verbose:
            self._print_commands(pip_cmd, stubtest_cmd, mypypath)

        return True
