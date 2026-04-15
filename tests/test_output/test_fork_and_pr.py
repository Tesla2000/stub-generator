import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

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
        with patch("subprocess.run", return_value=_make_git_mock()):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        target = Path(self.clone_dir) / "pkg" / "__init__.pyi"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "def foo() -> None: ...\n")

    def test_creates_py_typed(self):
        stub = self._make_stub("pkg/__init__.pyi")
        with patch("subprocess.run", return_value=_make_git_mock()):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        self.assertTrue((Path(self.clone_dir) / "pkg" / "py.typed").exists())

    def test_skips_existing_py_typed(self):
        stub = self._make_stub("pkg/__init__.pyi")
        py_typed = Path(self.clone_dir) / "pkg" / "py.typed"
        py_typed.parent.mkdir(parents=True, exist_ok=True)
        py_typed.touch()
        calls = []
        with patch(
            "subprocess.run",
            side_effect=lambda cmd, **kw: calls.append(cmd)
            or _make_git_mock(),
        ):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        added = [c for c in calls if "add" in c]
        self.assertFalse(any("py.typed" in str(c) for c in added))

    def test_stages_pyi_and_py_typed_via_git(self):
        stub = self._make_stub("pkg/mod.pyi")
        staged = []

        def fake_run(cmd, **kw):
            staged.append(cmd)
            return _make_git_mock()

        with patch("subprocess.run", side_effect=fake_run):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        add_args = [c for c in staged if "add" in c]
        staged_files = [c[-1] for c in add_args]
        self.assertTrue(any(".pyi" in f for f in staged_files))
        self.assertTrue(any("py.typed" in f for f in staged_files))

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
        return _StubTuple(py_path=pyi.with_suffix(".py"), pyi_path=pyi)

    def test_calls_merge_pyi_with_correct_paths(self):
        stub = self._make_stub("pkg/mod.pyi")
        calls = []
        with patch(
            "subprocess.run",
            side_effect=lambda cmd, **kw: calls.append(cmd)
            or _make_git_mock(),
        ):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        merge_calls = [c for c in calls if "merge-pyi" in c]
        self.assertEqual(len(merge_calls), 1)
        cmd = merge_calls[0]
        self.assertIn(str(Path(self.clone_dir) / "pkg" / "mod.py"), cmd)
        self.assertIn(str(stub.pyi_path.absolute()), cmd)

    def test_stages_py_file_via_git(self):
        stub = self._make_stub("pkg/mod.pyi")
        staged = []
        with patch(
            "subprocess.run",
            side_effect=lambda cmd, **kw: staged.append(cmd)
            or _make_git_mock(),
        ):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        add_args = [c for c in staged if "add" in c]
        self.assertTrue(any("mod.py" in str(c) for c in add_args))

    def test_creates_py_typed(self):
        stub = self._make_stub("pkg/mod.pyi")
        with patch("subprocess.run", return_value=_make_git_mock()):
            self.service._stage_files([stub], self.clone_dir, self.stubs_root)
        self.assertTrue((Path(self.clone_dir) / "pkg" / "py.typed").exists())

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
