from collections.abc import Collection
from typing import TypeVar

from stub_added._stub_tuple import _StubTuple

_StubTuples = TypeVar("_StubTuples", bound=Collection[_StubTuple])
