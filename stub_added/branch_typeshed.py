import subprocess
from contextlib import suppress
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field
from pydantic_logger import PydanticLogger


class BranchTypeshed(BaseModel):
    """Service for updating typeshed and creating new branches."""

    logger: PydanticLogger = Field(
        default_factory=lambda: PydanticLogger(name=__name__)
    )

    @staticmethod
    def _run_git_command(typeshed_path: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(typeshed_path), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _update_typeshed(self, typeshed_path: Path) -> str:
        self.logger.debug(f"Updating typeshed at {typeshed_path}...")

        # Fetch latest changes from remote
        self._run_git_command(typeshed_path, "fetch", "origin")
        self.logger.debug("Fetched latest changes from origin")

        # Get current branch name
        try:
            current_branch = self._run_git_command(
                typeshed_path, "rev-parse", "--abbrev-ref", "HEAD"
            )
        except subprocess.CalledProcessError:
            # If we're in detached HEAD state, checkout main/master
            current_branch = None

        self._run_git_command(
            typeshed_path, "rev-parse", "--verify", "origin/main"
        )
        main_branch = "main"

        # Checkout main branch if not already on it
        if current_branch != main_branch:
            self._run_git_command(typeshed_path, "checkout", main_branch)
            self.logger.debug(f"Checked out {main_branch} branch")

        # Pull latest changes
        self._run_git_command(typeshed_path, "pull", "origin", main_branch)
        self.logger.debug(f"Pulled latest changes from origin/{main_branch}")

        # Get current commit hash
        commit_hash = self._run_git_command(typeshed_path, "rev-parse", "HEAD")
        self.logger.debug(f"Updated to commit: {commit_hash}")

        return commit_hash

    def _create_branch(self, branch_name: str, typeshed_path: Path) -> str:
        self.logger.debug(f"Creating branch '{branch_name}' in typeshed...")

        with suppress(subprocess.CalledProcessError):
            self._run_git_command(
                typeshed_path, "rev-parse", "--verify", branch_name
            )
            raise ValueError(f"Branch '{branch_name}' already exists")

        # Create and checkout new branch
        self._run_git_command(typeshed_path, "checkout", "-b", branch_name)
        self.logger.debug(f"Created and checked out branch: {branch_name}")

        return branch_name

    def branch(self, branch_name: str, typeshed_path: Path) -> None:
        commit_hash = self._update_typeshed(typeshed_path)
        created_branch = self._create_branch(branch_name, typeshed_path)
        self.logger.debug("\nSuccess!")
        self.logger.debug(f"  Commit: {commit_hash}")
        self.logger.debug(f"  Branch: {created_branch}")
