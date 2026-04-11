from typing import Annotated
from typing import Union

from pydantic import Discriminator

from stub_adder.transformer.error_generator._flake8 import Flake8
from stub_adder.transformer.error_generator._mypy import Mypy
from stub_adder.transformer.error_generator._pyright import Pyright
from stub_adder.transformer.error_generator._ruff import Ruff

AnyGenerator = Annotated[
    Union[Flake8, Mypy, Pyright, Ruff], Discriminator("type")
]

__all__ = [
    "AnyGenerator",
    "Flake8",
    "Mypy",
    "Pyright",
    "Ruff",
]
