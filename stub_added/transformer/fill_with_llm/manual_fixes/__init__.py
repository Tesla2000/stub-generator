from typing import Annotated
from typing import Union

from pydantic import Tag
from stub_added.transformer.fill_with_llm.manual_fixes._base import ManualFix
from stub_added.transformer.fill_with_llm.manual_fixes.import_fixer import (
    ImportFixer,
)
from stub_added.transformer.fill_with_llm.manual_fixes.lsp_violation_fixer import (
    LspViolationFixer,
)

AnyManualFix = Annotated[
    Union[
        Annotated[LspViolationFixer, Tag("lsp")],
        Annotated[ImportFixer, Tag("import")],
    ],
    ...,
]

DEFAULT_MANUAL_FIXES: tuple[AnyManualFix, ...] = (
    LspViolationFixer(),
    ImportFixer(),
)

__all__ = [
    "AnyManualFix",
    "DEFAULT_MANUAL_FIXES",
    "ManualFix",
    "LspViolationFixer",
    "ImportFixer",
]
