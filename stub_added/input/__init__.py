from enum import auto
from enum import StrEnum
from typing import Union

from stub_added.input.existing_stubs_reader import ExistingStubsReader
from stub_added.input.stub_generator import StubGenerator


class InputType(StrEnum):
    STUB_GENERATOR = auto()
    EXISTING_STUBS = auto()


AnyInput = Union[StubGenerator, ExistingStubsReader]
