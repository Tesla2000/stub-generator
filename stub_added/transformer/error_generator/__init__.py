from typing import Union

from stub_added.transformer.error_generator._mypy import Mypy
from stub_added.transformer.error_generator._pyright import Pyright

AnyGenerator = Union[Mypy, Pyright]

__all__ = [
    "AnyGenerator",
    "Mypy",
    "Pyright",
]
