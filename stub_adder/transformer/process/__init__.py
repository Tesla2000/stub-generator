from typing import Union

from stub_adder.transformer.process._black import Black
from stub_adder.transformer.process._pyupgrade import Pyupgrade
from stub_adder.transformer.process._ruff_isort import RuffIsort

AnyProcess = Union[Black, Pyupgrade, RuffIsort]

__all__ = [
    "AnyProcess",
    "Black",
    "Pyupgrade",
    "RuffIsort",
]
