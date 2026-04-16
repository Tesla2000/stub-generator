from typing import Union

from stub_adder.input.existing_stubs_reader import ExistingStubsReader
from stub_adder.input.stub_generator import StubGenerator

AnyInput = Union[StubGenerator, ExistingStubsReader]

__all__ = [
    "AnyInput",
    "StubGenerator",
    "ExistingStubsReader",
]
