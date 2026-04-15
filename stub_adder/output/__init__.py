from enum import auto
from enum import StrEnum
from typing import Union

from stub_adder.output._fork_and_pr_base import ForkAndPRBase
from stub_adder.output.branch_typeshed import BranchTypeshed
from stub_adder.output.directory_output import DirectoryOutput
from stub_adder.output.fork_and_pr_merge_py import ForkAndPRMergePy
from stub_adder.output.fork_and_pr_pyi import ForkAndPRPyi


class OutputType(StrEnum):
    BRANCH_TYPESHED = auto()
    DIRECTORY = auto()
    FORK_AND_PR_PYI = auto()
    FORK_AND_PR_MERGE_PY = auto()


AnyOutput = Union[
    BranchTypeshed, DirectoryOutput, ForkAndPRPyi, ForkAndPRMergePy
]

__all__ = [
    "AnyOutput",
    "BranchTypeshed",
    "DirectoryOutput",
    "ForkAndPRBase",
    "ForkAndPRMergePy",
    "ForkAndPRPyi",
    "OutputType",
]
