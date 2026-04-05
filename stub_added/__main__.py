import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import CliApp
from pydantic_settings import SettingsConfigDict
from stub_added.input import AnyInput
from stub_added.output import AnyOutput
from stub_added.transformer import AnyTransformer
from stub_added.transformer.no_op_transformer import NoOpTransformer


class Main(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    output_path: Path = Field(
        default_factory=lambda: Path(tempfile.TemporaryDirectory().name)
    )

    input: AnyInput
    transformer: AnyTransformer = Field(default_factory=NoOpTransformer)
    outputs: tuple[AnyOutput, ...] = Field(min_length=1)

    async def cli_cmd(self) -> None:
        stub_tuples = tuple(self.input.generate(self.output_path))
        transformed_tuples = self.transformer.transform(
            stub_tuples, self.output_path
        )
        for output in self.outputs:
            output.save(transformed_tuples, self.output_path)


if __name__ == "__main__":
    load_dotenv(os.getenv("ENV_FILE", ".env"))
    CliApp.run(Main)
