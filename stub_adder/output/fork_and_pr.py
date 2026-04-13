import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from shutil import copy2
from typing import Annotated
from typing import Literal

from github import Github
from github.Repository import Repository
from pydantic import AfterValidator
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr
from pydantic_logger import PydanticLogger

from stub_adder._stub_tuple import _StubTuple


def _validate_repo_name(v: str) -> str:
    parts = v.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"repo_name must be in 'owner/repo' format, got {v!r}"
        )
    return v


RepoName = Annotated[
    str,
    AfterValidator(_validate_repo_name),
    Field(description="Target repository in 'owner/repo' format"),
]

GithubToken = Annotated[
    SecretStr,
    Field(description="GitHub personal access token with repo scope"),
]


class ForkAndPR(BaseModel):
    """Forks a repository, commits stub changes on a new branch, and opens a draft PR."""

    model_config = ConfigDict(frozen=True)

    type: Literal["fork_and_pr"] = "fork_and_pr"
    repo_name: RepoName
    github_token: GithubToken
    branch_name: str = Field(
        default="python-interface",
        description="Branch name to create in the fork",
    )
    logger: PydanticLogger = PydanticLogger(name=__name__)

    def _git(self, repo_dir: str, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", repo_dir, *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def save(
        self, stub_tuples: Iterable[_StubTuple], stubs_root: Path
    ) -> Repository:
        token = self.github_token.get_secret_value()
        gh = Github(token)
        upstream = gh.get_repo(self.repo_name)
        user = gh.get_user()

        fork = user.create_fork(upstream)
        self.logger.debug(f"Forked {upstream.full_name} -> {fork.full_name}")

        authenticated_url = fork.clone_url.replace(
            "https://", f"https://{token}@"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            self.logger.debug(f"Cloning fork into {tmp_dir}...")
            self._git(tmp_dir, "init")
            self._git(tmp_dir, "remote", "add", "origin", authenticated_url)
            self._git(tmp_dir, "fetch", "origin")

            default_branch = fork.default_branch
            self._git(tmp_dir, "checkout", default_branch)
            self._git(tmp_dir, "pull", "origin", default_branch)
            self.logger.debug(f"Checked out {default_branch}")

            self._git(tmp_dir, "checkout", "-b", self.branch_name)
            self.logger.debug(f"Created branch {self.branch_name}")

            for stub_tuple in stub_tuples:
                relative = stub_tuple.pyi_path.relative_to(stubs_root)
                target = Path(tmp_dir) / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                copy2(stub_tuple.pyi_path, target)
                self._git(
                    tmp_dir,
                    "add",
                    str(target.relative_to(tmp_dir)),
                )
                self.logger.debug(f"Staged {target}")

            self._git(
                tmp_dir,
                "commit",
                "-m",
                f"Add type stubs for {self.branch_name}",
            )
            try:
                self._git(tmp_dir, "push", "-u", "origin", self.branch_name)
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to push, branch already exists")
            else:
                self.logger.debug(f"Pushed branch {self.branch_name} to fork")

        return fork
