import subprocess
from pathlib import Path
from typing import Annotated
from typing import Literal

from github import Github
from github import GithubException
from pydantic import Field
from pydantic import SecretStr

from stub_adder.input.version_extractor._base import VersionExtractorBase

GithubToken = Annotated[
    SecretStr,
    Field(
        description="GitHub personal access token (optional, avoids rate limits)"
    ),
]


class GithubReleaseExtractor(VersionExtractorBase):
    type: Literal["github_release"] = "github_release"
    repo_name: str = Field(description="Repository in 'owner/repo' format")
    github_token: GithubToken | None = None

    def __call__(self, repo_path: Path) -> str | None:
        token = (
            self.github_token.get_secret_value() if self.github_token else None
        )
        # Bad credentials or unknown repo propagate — input/config errors
        repo = Github(token).get_repo(self.repo_name)

        # EAFP: repo may simply have no releases yet
        try:
            release = repo.get_latest_release()
        except GithubException:
            return None

        tag = release.tag_name
        # Checkout must succeed — failure means misconfigured clone, propagate
        subprocess.run(
            ["git", "-C", str(repo_path), "checkout", tag],
            check=True,
            capture_output=True,
        )
        return tag.lstrip("v")
