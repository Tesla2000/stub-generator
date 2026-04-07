from typing import Annotated
from typing import Union

from pydantic import Field
from stub_added.transformer.file_fix._base import ManualFix
from stub_added.transformer.file_fix.abstract_class_fixer import (
    AbstractClassFixer,
)
from stub_added.transformer.file_fix.callable_to_async_def import (
    CallableToAsyncDef,
)
from stub_added.transformer.file_fix.import_fixer import ImportFixer
from stub_added.transformer.file_fix.lsp_violation_fixer import (
    LspViolationFixer,
)
from stub_added.transformer.file_fix.mro_conflict_fixer import MroConflictFixer

AnyManualFix = Annotated[
    Union[
        LspViolationFixer,
        ImportFixer,
        MroConflictFixer,
        CallableToAsyncDef,
        AbstractClassFixer,
    ],
    Field(discriminator="type"),
]

__all__ = [
    "AbstractClassFixer",
    "AnyManualFix",
    "CallableToAsyncDef",
    "ManualFix",
    "ImportFixer",
    "LspViolationFixer",
    "MroConflictFixer",
]
