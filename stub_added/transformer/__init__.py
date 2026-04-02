from enum import auto
from enum import StrEnum
from typing import Union

from stub_added.transformer.fill_with_llm import FillWithLLM
from stub_added.transformer.no_op_transformer import NoOpTransformer


class TransformerType(StrEnum):
    FILL_WITH_LLM = auto()
    NO_OP = auto()


AnyTransformer = Union[FillWithLLM, NoOpTransformer]
