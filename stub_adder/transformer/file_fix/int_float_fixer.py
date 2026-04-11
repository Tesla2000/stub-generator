import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar
from typing import Literal

from stub_adder.transformer.file_fix._base import ManualFix


class IntFloatFixer(ManualFix):
    """Fix flake8-pyi Y041: replace ``int | float`` with ``float``.

    PEP 484 specifies that ``float`` already accepts ``int`` via the numeric
    tower, so ``int | float`` and ``Union[int, float]`` are redundant.
    """

    type: Literal["int_float"] = "int_float"
    _Y041_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bY041\b")

    # Order matters: try more-specific patterns first.
    _REPLACEMENTS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        (re.compile(r"\bUnion\[int,\s*float\]"), "float"),
        (re.compile(r"\bUnion\[float,\s*int\]"), "float"),
        (re.compile(r"\bint\s*\|\s*float\b"), "float"),
        (re.compile(r"\bfloat\s*\|\s*int\b"), "float"),
    ]

    def is_applicable(self, errors: Iterable[str]) -> bool:
        return any(self._Y041_RE.search(e) for e in errors)

    def __call__(
        self, contents: str, errors: list[str], stubs_dir: Path | None = None
    ) -> str:
        if not any(self._Y041_RE.search(e) for e in errors):
            return contents

        for pattern, replacement in self._REPLACEMENTS:
            contents = pattern.sub(replacement, contents)

        return contents
