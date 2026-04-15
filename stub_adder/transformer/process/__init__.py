from typing import Union

from stub_adder.transformer.process._base import ProcessBase
from stub_adder.transformer.process._black import Black
from stub_adder.transformer.process._pyupgrade import Pyupgrade
from stub_adder.transformer.process._ruff_fix import RuffFix
from stub_adder.transformer.process._string_annotation_unquoter import (
    StringAnnotationUnquoter,
)
from stub_adder.transformer.process._unused_import_remover import (
    UnusedImportRemover,
)

AnyProcess = Union[
    Black, Pyupgrade, RuffFix, StringAnnotationUnquoter, UnusedImportRemover
]

__all__ = [
    "AnyProcess",
    "Black",
    "ProcessBase",
    "Pyupgrade",
    "RuffFix",
    "StringAnnotationUnquoter",
    "UnusedImportRemover",
]
