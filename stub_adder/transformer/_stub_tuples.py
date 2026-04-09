from collections.abc import Collection
from typing import TypeVar

from stub_adder._stub_tuple import _StubTuple

_StubTuples = TypeVar("_StubTuples", bound=Collection[_StubTuple])
