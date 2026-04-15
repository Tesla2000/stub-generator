import subprocess
import tempfile
from abc import abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

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


class ForkAndPRBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_name: RepoName
    github_token: GithubToken
    branch_name: str = Field(
        default="python-interface",
        description="Branch name to create in the fork",
    )
    commit_message: str
    logger: PydanticLogger = PydanticLogger(name=__name__)

    def _git(self, repo_dir: str, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", repo_dir, *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _stage_py_typed(self, tmp_dir: str, directory: Path) -> Path | None:
        py_typed = directory / "py.typed"
        if not py_typed.exists():
            py_typed.touch()
            return py_typed.relative_to(tmp_dir)
        return None

    @abstractmethod
    def _stage_files(
        self,
        stub_tuples: Iterable[_StubTuple],
        tmp_dir: str,
        stubs_root: Path,
    ) -> Iterable[Path]: ...

    def save(
        self, stub_tuples: Iterable[_StubTuple], stubs_root: Path
    ) -> Repository:
        token = self.github_token.get_secret_value()
        gh = Github(token)
        upstream = gh.get_repo(self.repo_name)
        user = gh.get_user()

        fork = user.create_fork(upstream)  # type: ignore[union-attr]
        self.logger.debug(f"Forked {upstream.full_name} -> {fork.full_name}")

        authenticated_url = fork.clone_url.replace(
            "https://", f"https://{token}@"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            default_branch = fork.default_branch
            self.logger.debug(f"Cloning fork into {tmp_dir}...")
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    "--branch",
                    default_branch,
                    authenticated_url,
                    tmp_dir,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.logger.debug(f"Checked out {default_branch}")

            self._git(tmp_dir, "checkout", "-b", self.branch_name)
            self.logger.debug(f"Created branch {self.branch_name}")

            paths = list(self._stage_files(stub_tuples, tmp_dir, stubs_root))
            self._git(tmp_dir, "add", *map(str, paths))
            self.logger.debug(f"Staged {len(paths)} files")

            self._git(
                tmp_dir,
                "commit",
                "-m",
                self.commit_message,
            )
            try:
                self._git(tmp_dir, "push", "-u", "origin", self.branch_name)
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to push, branch already exists")
            else:
                self.logger.debug(f"Pushed branch {self.branch_name} to fork")

        return fork
