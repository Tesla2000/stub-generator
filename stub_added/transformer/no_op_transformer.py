from typing import Literal

from pydantic import BaseModel
from stub_added.transformer._stub_tuples import _StubTuples
from stub_added.transformer.transformer_type import TransformerType


class NoOpTransformer(BaseModel):
    type: Literal[TransformerType.NO_OP] = TransformerType.NO_OP

    def transform(self, stub_tuples: _StubTuples) -> _StubTuples:
        return stub_tuples
