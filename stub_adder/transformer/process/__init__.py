from typing import Union

from stub_adder.transformer.process._any_replacer import AnyReplacer
from stub_adder.transformer.process._base import ProcessBase
from stub_adder.transformer.process._black import Black
from stub_adder.transformer.process._duplicate_import_remover import (
    DuplicateImportRemover,
)
from stub_adder.transformer.process._pre_commit_hooks import PreCommitHooks
from stub_adder.transformer.process._pyupgrade import Pyupgrade
from stub_adder.transformer.process._ruff_fix import RuffFix
from stub_adder.transformer.process._string_annotation_unquoter import (
    StringAnnotationUnquoter,
)
from stub_adder.transformer.process._unused_import_remover import (
    UnusedImportRemover,
)

AnyProcess = Union[
    AnyReplacer,
    Black,
    DuplicateImportRemover,
    Pyupgrade,
    RuffFix,
    StringAnnotationUnquoter,
    UnusedImportRemover,
    PreCommitHooks,
]

__all__ = [
    "AnyProcess",
    "AnyReplacer",
    "Black",
    "DuplicateImportRemover",
    "ProcessBase",
    "Pyupgrade",
    "RuffFix",
    "StringAnnotationUnquoter",
    "UnusedImportRemover",
    "PreCommitHooks",
]
