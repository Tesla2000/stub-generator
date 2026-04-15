import subprocess
from pathlib import Path
from typing import Literal

from stub_adder.transformer.process._base import ProcessBase


class RuffFix(ProcessBase):
    type: Literal["ruff_fix"] = "ruff_fix"
    select: tuple[str, ...] = ()
    extend_select: tuple[str, ...] = ("I",)
    unsafe_fixes: bool = False

    def process(self, pyi_paths: list[Path]) -> None:
        cmd = ["ruff", "check", "--fix"]
        if self.select:
            cmd.append(f"--select={','.join(self.select)}")
        if self.extend_select:
            cmd.append(f"--extend-select={','.join(self.extend_select)}")
        if self.unsafe_fixes:
            cmd.append("--unsafe-fixes")
        subprocess.run(
            cmd + list(map(str, pyi_paths)),
            capture_output=True,
        )
