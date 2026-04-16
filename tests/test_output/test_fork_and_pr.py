import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from stub_adder._stub_tuple import _StubTuple
from stub_adder.output.fork_and_pr_merge_py import ForkAndPRMergePy
from stub_adder.output.fork_and_pr_pyi import ForkAndPRPyi


def _make_git_mock(stdout: str = "") -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = 0
    return m


class TestForkAndPRPyiStageFiles(TestCase):
    def setUp(self) -> None:
        self._stubs_tmp = tempfile.TemporaryDirectory()
        self._clone_tmp = tempfile.TemporaryDirectory()
        self.stubs_root = Path(self._stubs_tmp.name)
        self.clone_dir = self._clone_tmp.name
        self.service = ForkAndPRPyi(
            repo_name="owner/repo",
            github_token=SecretStr("token"),
        )

    def tearDown(self) -> None:
        self._stubs_tmp.cleanup()
        self._clone_tmp.cleanup()

    def _make_stub(self, relative: str) -> _StubTuple:
        pyi = self.stubs_root / relative
        pyi.parent.mkdir(parents=True, exist_ok=True)
        pyi.write_text("def foo() -> None: ...\n")
        return _StubTuple(py_path=pyi.with_suffix(".py"), pyi_path=pyi)

    def test_copies_pyi_to_clone(self):
        stub = self._make_stub("pkg/__init__.pyi")
        list(
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        )
        target = Path(self.clone_dir) / "pkg" / "__init__.pyi"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "def foo() -> None: ...\n")

    def test_returns_relative_pyi_path(self):
        stub = self._make_stub("pkg/mod.pyi")
        result = list(
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        )
        self.assertEqual(len(result), 1)
        self.assertIn(".pyi", str(result[0]))

    def test_type_is_fork_and_pr_pyi(self):
        self.assertEqual(self.service.type, "fork_and_pr_pyi")


class TestForkAndPRMergePyStageFiles(TestCase):
    def setUp(self) -> None:
        self._stubs_tmp = tempfile.TemporaryDirectory()
        self._clone_tmp = tempfile.TemporaryDirectory()
        self.stubs_root = Path(self._stubs_tmp.name)
        self.clone_dir = self._clone_tmp.name
        self.service = ForkAndPRMergePy(
            repo_name="owner/repo",
            github_token=SecretStr("token"),
        )

    def tearDown(self) -> None:
        self._stubs_tmp.cleanup()
        self._clone_tmp.cleanup()

    def _make_stub(self, relative: str) -> _StubTuple:
        pyi = self.stubs_root / relative
        pyi.parent.mkdir(parents=True, exist_ok=True)
        pyi.write_text("def foo() -> None: ...\n")
        py = pyi.with_suffix(".py")
        py.write_text("def foo(): pass\n")
        return _StubTuple(py_path=py, pyi_path=pyi)

    def test_calls_merge_pyi_with_correct_paths(self):
        stub = self._make_stub("pkg/mod.pyi")
        calls = []
        with patch(
            "subprocess.run",
            side_effect=lambda cmd, **kw: calls.append(cmd)
            or _make_git_mock(),
        ):
            list(
                self.service._stage_files(
                    [stub], self.clone_dir, self.stubs_root
                )
            )
        merge_calls = [c for c in calls if "merge-pyi" in c]
        self.assertEqual(len(merge_calls), 1)
        cmd = merge_calls[0]
        self.assertIn(str(Path(self.clone_dir) / "pkg" / "mod.py"), cmd)
        self.assertIn(str(stub.pyi_path.absolute()), cmd)

    def test_returns_relative_py_path(self):
        stub = self._make_stub("pkg/mod.pyi")
        with patch("subprocess.run", return_value=_make_git_mock()):
            result = list(
                self.service._stage_files(
                    [stub], self.clone_dir, self.stubs_root
                )
            )
        self.assertEqual(len(result), 1)
        self.assertIn("mod.py", str(result[0]))

    def test_type_is_fork_and_pr_merge_py(self):
        self.assertEqual(self.service.type, "fork_and_pr_merge_py")


@pytest.mark.skipif(
    not os.getenv("RUN_MANUAL"), reason="Manual test — set RUN_MANUAL to run"
)
def test_push_pyi_to_fork() -> None:
    with tempfile.TemporaryDirectory() as stubs_root_str:
        stubs_root = Path(stubs_root_str)
        dummy = stubs_root / "pyphen" / "__init__.pyi"
        dummy.parent.mkdir(parents=True, exist_ok=True)
        dummy.write_text("")
        output = ForkAndPRPyi(
            repo_name="Kozea/Pyphen",
            github_token=SecretStr(os.environ["GITHUB_TOKEN"]),
        )
        fork = None
        try:
            fork = output.save([_StubTuple(dummy, dummy)], stubs_root)
        finally:
            if fork:
                fork.delete()
