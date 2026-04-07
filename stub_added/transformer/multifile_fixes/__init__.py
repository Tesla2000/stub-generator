from typing import Annotated
from typing import Union

from pydantic import Field
from stub_added.transformer.multifile_fixes._any_base_fixer import AnyBaseFixer
from stub_added.transformer.multifile_fixes._base import MultiFileFix
from stub_added.transformer.multifile_fixes._coroutine_return_fixer import (
    CoroutineReturnFixer,
)
from stub_added.transformer.multifile_fixes._llm_fixer import LlmFixer

AnyMultiFileFix = Annotated[
    Union[AnyBaseFixer, CoroutineReturnFixer, LlmFixer],
    Field(discriminator="type"),
]

__all__ = [
    "AnyBaseFixer",
    "AnyMultiFileFix",
    "CoroutineReturnFixer",
    "LlmFixer",
    "MultiFileFix",
]
