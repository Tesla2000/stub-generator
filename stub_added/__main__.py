from pathlib import Path

from pydantic import Field
from pydantic import HttpUrl
from pydantic_settings import BaseSettings
from pydantic_settings import CliApp
from pydantic_settings import SettingsConfigDict
from stub_added.branch_typeshed import BranchTypeshed
from stub_added.stub_generator import StubGenerator


class Main(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    typeshed_path: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent / "typeshed",
        description="Path to the typeshed submodule directory",
    )
    stubbed_repo_url: HttpUrl
    branch_creator: BranchTypeshed = Field(default_factory=BranchTypeshed)
    stub_generator: StubGenerator = Field(default_factory=StubGenerator)

    async def cli_cmd(self) -> None:
        self.branch_creator.branch(
            str(self.stubbed_repo_url).split("/")[-1], self.typeshed_path
        )
        self.stub_generator.generate(self.stubbed_repo_url, self.typeshed_path)


if __name__ == "__main__":
    CliApp.run(Main)
