import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_logger import LoggingConfig
from pydantic_settings import BaseSettings
from pydantic_settings import CliApp
from pydantic_settings import SettingsConfigDict

from stub_adder.input import AnyInput
from stub_adder.output import AnyOutput
from stub_adder.transformer import FixErrors


class Main(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    output_path: Path

    logging_config: LoggingConfig = LoggingConfig(level="DEBUG")

    input: AnyInput
    transformer: FixErrors = Field(default_factory=FixErrors)
    outputs: tuple[AnyOutput, ...] = Field(min_length=1)

    async def cli_cmd(self) -> None:
        self.logging_config.apply()
        stub_tuples = tuple(self.input.generate(self.output_path))
        transformed_tuples = self.transformer.transform(
            stub_tuples, self.output_path
        )
        for output in self.outputs:
            output.save(transformed_tuples, self.output_path)


if __name__ == "__main__":
    load_dotenv(os.getenv("ENV_FILE", ".env"))
    CliApp.run(Main)
