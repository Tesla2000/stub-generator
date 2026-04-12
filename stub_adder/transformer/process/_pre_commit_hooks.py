from pathlib import Path
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class PreCommitHooks(BaseModel):
    """Apply the file-modifying pre-commit-hooks used in typeshed.

    Mirrors these hooks from typeshed's .pre-commit-config.yaml:
      - trailing-whitespace
      - end-of-file-fixer
      - mixed-line-ending (--fix=lf)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    type: Literal["pre_commit_hooks"] = "pre_commit_hooks"

    @staticmethod
    def _fix_contents(contents: str) -> str:
        # Normalize line endings to LF
        contents = contents.replace("\r\n", "\n").replace("\r", "\n")
        # Strip trailing whitespace from each line
        lines = [line.rstrip(" \t") for line in contents.split("\n")]
        # Rejoin and ensure exactly one trailing newline
        result = "\n".join(lines).rstrip("\n") + "\n"
        return result

    def process(self, pyi_paths: list[Path]) -> None:
        for path in pyi_paths:
            original = path.read_text(encoding="utf-8")
            fixed = self._fix_contents(original)
            if fixed != original:
                path.write_text(fixed, encoding="utf-8")
