from pydantic import BaseModel
from stub_added.transformer._stub_tuples import _StubTuples


class NoOpTransformer(BaseModel):

    def transform(self, stub_tuples: _StubTuples) -> _StubTuples:
        return stub_tuples
