import contextlib
import io
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.error_generator._base import ErrorGeneratorBase
from typeshed.tests.stubtest_third_party import run_stubtest

_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")


class Stubtest(ErrorGeneratorBase):
    type: Literal["stubtest"] = "stubtest"
    ci_platforms_only: bool = True
    _ERROR_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^error: (\S+)", re.MULTILINE
    )

    def generate(
        self, pyi_paths: list[Path], stubs_dir: Path
    ) -> dict[Path, list[str]]:
        stubs_dir = stubs_dir.resolve()
        typeshed_dir = stubs_dir.parent.parent

        buffer = io.StringIO()
        old_cwd = os.getcwd()
        try:
            os.chdir(typeshed_dir)
            with contextlib.redirect_stdout(buffer):
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
