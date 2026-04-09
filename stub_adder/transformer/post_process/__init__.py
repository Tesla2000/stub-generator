from typing import Union

from stub_adder.transformer.post_process._black import Black
from stub_adder.transformer.post_process._pyupgrade import Pyupgrade

AnyPostProcess = Union[Black, Pyupgrade]

__all__ = [
    "AnyPostProcess",
    "Black",
    "Pyupgrade",
]
