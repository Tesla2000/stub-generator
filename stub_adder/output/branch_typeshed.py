import subprocess
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from shutil import copy2
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple


class BranchTypeshed(BaseModel):
    """Service for updating typeshed and creating new branches."""

    model_config = ConfigDict(frozen=True)

    type: Literal["branch_typeshed"] = "branch_typeshed"
    typeshed_path: Path = Field(
        Path("typeshed"),
        description="Path to the typeshed submodule directory",
    )
    logger: PydanticLogger = Field(
        default_factory=lambda: PydanticLogger(name=__name__)
    )
    branch_name: str

    def _run_git_command(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.typeshed_path), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _update_typeshed(self) -> str:
        self.logger.debug(f"Updating typeshed at {self.typeshed_path}...")

        # Fetch latest changes from remote
        self._run_git_command("fetch", "origin")
        self.logger.debug("Fetched latest changes from origin")

        # Get current branch name
        try:
            current_branch = self._run_git_command(
                "rev-parse", "--abbrev-ref", "HEAD"
            )
        except subprocess.CalledProcessError:
            # If we're in detached HEAD state, checkout main/master
            current_branch = None

        self._run_git_command("rev-parse", "--verify", "origin/main")
        main_branch = "main"

        # Checkout main branch if not already on it
        if current_branch != main_branch:
            self._run_git_command("checkout", main_branch)
            self.logger.debug(f"Checked out {main_branch} branch")

        # Pull latest changes
        self._run_git_command("pull", "origin", main_branch)
        self.logger.debug(f"Pulled latest changes from origin/{main_branch}")

        # Get current commit hash
        commit_hash = self._run_git_command("rev-parse", "HEAD")
        self.logger.debug(f"Updated to commit: {commit_hash}")

        return commit_hash

    def _create_branch(self, branch_name: str) -> str:
        self.logger.debug(f"Creating branch '{branch_name}' in typeshed...")

        with suppress(subprocess.CalledProcessError):
            self._run_git_command("rev-parse", "--verify", branch_name)
            raise ValueError(f"Branch '{branch_name}' already exists")

        # Create and checkout new branch
        self._run_git_command("checkout", "-b", branch_name)
        self.logger.debug(f"Created and checked out branch: {branch_name}")

        return branch_name

    def _add_stub_files(
        self, stub_tuples: Iterable[_StubTuple], stubs_root: Path
    ) -> None:
        for stub_tuple in stub_tuples:
            relative = stub_tuple.pyi_path.relative_to(stubs_root)
            target = self.typeshed_path / "stubs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(stub_tuple.pyi_path, target)
            self._run_git_command(
                "add", str(target.relative_to(self.typeshed_path))
            )
            self.logger.debug(f"Staged stub file: {target}")

        self._run_git_command(
            "commit", "-m", f"Add type stubs for {self.branch_name}"
        )
        self.logger.debug("Committed stub files")

    def _push_branch(self) -> None:
        self._run_git_command("push", "-u", "origin", self.branch_name)
        self.logger.debug(f"Pushed branch '{self.branch_name}' to origin")

    def save(
        self, stub_tuples: Iterable[_StubTuple], stubs_root: Path
    ) -> None:
        commit_hash = self._update_typeshed()
        created_branch = self._create_branch(self.branch_name)
        self._add_stub_files(stub_tuples, stubs_root)
        self._push_branch()
        self.logger.debug("\nSuccess!")
        self.logger.debug(f"  Commit: {commit_hash}")
        self.logger.debug(f"  Branch: {created_branch}")
