from collections.abc import Iterable
from pathlib import Path
from shutil import copy2
from typing import Literal

from stub_adder._stub_tuple import _StubTuple
from stub_adder.output._fork_and_pr_base import ForkAndPRBase


class ForkAndPRPyi(ForkAndPRBase):
    """Forks a repo, pushes .pyi stub files on a new branch, and opens a draft PR."""

    type: Literal["fork_and_pr_pyi"] = "fork_and_pr_pyi"
    commit_message: str = "Added stub files"

    def _stage_files(
        self,
        stub_tuples: Iterable[_StubTuple],
        tmp_dir: str,
        stubs_root: Path,
    ) -> Iterable[Path]:
        for stub_tuple in stub_tuples:
            pyi_path = stub_tuple.pyi_path.absolute()
            relative = pyi_path.relative_to(stubs_root.absolute())
            target = Path(tmp_dir) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(pyi_path, target)
            yield target.relative_to(tmp_dir)
            py_typed = self._stage_py_typed(tmp_dir, target.parent)
            if py_typed is not None:
                yield py_typed
