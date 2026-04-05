from typing import Union

from stub_added.transformer.fill_with_llm import FillWithLLM
from stub_added.transformer.no_op_transformer import NoOpTransformer

AnyTransformer = Union[FillWithLLM, NoOpTransformer]
