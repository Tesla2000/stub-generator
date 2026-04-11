from typing import Union

from stub_adder.transformer.process._black import Black
from stub_adder.transformer.process._pyupgrade import Pyupgrade

AnyProcess = Union[Black, Pyupgrade]

__all__ = [
    "AnyProcess",
    "Black",
    "Pyupgrade",
]
