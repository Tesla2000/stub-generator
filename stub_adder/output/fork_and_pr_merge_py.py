import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from stub_adder._stub_tuple import _StubTuple
from stub_adder.output._fork_and_pr_base import ForkAndPRBase


class ForkAndPRMergePy(ForkAndPRBase):
    """Forks a repo, merges stub types into .py sources via merge-pyi, and opens a draft PR."""

    type: Literal["fork_and_pr_merge_py"] = "fork_and_pr_merge_py"
    commit_message: str = "Added missing types"

    def _stage_files(
        self,
        stub_tuples: Iterable[_StubTuple],
        tmp_dir: str,
        stubs_root: Path,
    ) -> Iterable[Path]:
        for stub_tuple in stub_tuples:
            pyi_path = stub_tuple.pyi_path.absolute()
            relative_py = pyi_path.relative_to(
                stubs_root.absolute()
            ).with_suffix(".py")
            target_py = Path(tmp_dir) / relative_py
            target_py.parent.mkdir(parents=True, exist_ok=True)
            target_py.write_text(stub_tuple.py_path.read_text())
            subprocess.run(
                ["merge-pyi", "--in-place", str(target_py), str(pyi_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            yield relative_py
            py_typed = self._stage_py_typed(tmp_dir, target_py.parent)
            if py_typed is not None:
                yield py_typed
