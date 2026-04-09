from typing import Union

from stub_adder.transformer.error_generator._mypy import Mypy
from stub_adder.transformer.error_generator._pyright import Pyright

AnyGenerator = Union[Mypy, Pyright]

__all__ = [
    "AnyGenerator",
    "Mypy",
    "Pyright",
]
