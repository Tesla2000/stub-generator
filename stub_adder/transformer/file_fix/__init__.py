from typing import Annotated
from typing import Union

from pydantic import Field

from stub_adder.transformer.file_fix._base import ManualFix
from stub_adder.transformer.file_fix.abstract_class_fixer import (
    AbstractClassFixer,
)
from stub_adder.transformer.file_fix.callable_to_async_def import (
    CallableToAsyncDef,
)
from stub_adder.transformer.file_fix.docstring_fixer import DocstringFixer
from stub_adder.transformer.file_fix.enter_return_self_fixer import (
    EnterReturnSelfFixer,
)
from stub_adder.transformer.file_fix.import_fixer import ImportFixer
from stub_adder.transformer.file_fix.int_float_fixer import IntFloatFixer
from stub_adder.transformer.file_fix.long_literal_fixer import LongLiteralFixer
from stub_adder.transformer.file_fix.lsp_violation_fixer import (
    LspViolationFixer,
)
from stub_adder.transformer.file_fix.mro_conflict_fixer import MroConflictFixer
from stub_adder.transformer.file_fix.mutable_default_fixer import (
    MutableDefaultFixer,
)
from stub_adder.transformer.file_fix.pyright_attribute_fixer import (
    PyrightAttributeFixer,
)
from stub_adder.transformer.file_fix.type_alias_fixer import TypeAliasFixer

AnyManualFix = Annotated[
    Union[
        LspViolationFixer,
        ImportFixer,
        MroConflictFixer,
        CallableToAsyncDef,
        AbstractClassFixer,
        PyrightAttributeFixer,
        MutableDefaultFixer,
        DocstringFixer,
        TypeAliasFixer,
        LongLiteralFixer,
        EnterReturnSelfFixer,
        IntFloatFixer,
    ],
    Field(discriminator="type"),
]

__all__ = [
    "AbstractClassFixer",
    "AnyManualFix",
    "CallableToAsyncDef",
    "DocstringFixer",
    "EnterReturnSelfFixer",
    "IntFloatFixer",
    "LongLiteralFixer",
    "ManualFix",
    "ImportFixer",
    "LspViolationFixer",
    "MroConflictFixer",
    "MutableDefaultFixer",
    "PyrightAttributeFixer",
    "TypeAliasFixer",
]
