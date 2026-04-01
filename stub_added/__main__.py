import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic import HttpUrl
from pydantic_settings import BaseSettings
from pydantic_settings import CliApp
from pydantic_settings import SettingsConfigDict
from stub_added.input.stub_generator import StubGenerator
from stub_added.output.branch_typeshed import BranchTypeshed
from stub_added.transformer.fill_with_llm import FillWithLLM


class Main(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    output_path: Path = Field(
        default_factory=lambda: Path(tempfile.TemporaryDirectory().name)
    )

    stubbed_repo_url: HttpUrl
    input: StubGenerator
    transformer: FillWithLLM = Field(default_factory=FillWithLLM)
    outputs: tuple[BranchTypeshed, ...]

    async def cli_cmd(self) -> None:
        stub_tuples = tuple(
            self.input.generate(self.stubbed_repo_url, self.output_path)
        )
        transformed_tuples = self.transformer.transform(stub_tuples)
        for output in self.outputs:
            output.save(transformed_tuples, self.output_path)


if __name__ == "__main__":
    load_dotenv(os.getenv("ENV_FILE", ".env"))
    CliApp.run(Main)
