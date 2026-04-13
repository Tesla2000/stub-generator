from enum import auto
from enum import StrEnum
from typing import Union

from stub_adder.output.branch_typeshed import BranchTypeshed
from stub_adder.output.directory_output import DirectoryOutput
from stub_adder.output.fork_and_pr import ForkAndPR


class OutputType(StrEnum):
    BRANCH_TYPESHED = auto()
    DIRECTORY = auto()
    FORK_AND_PR = auto()


AnyOutput = Union[BranchTypeshed, DirectoryOutput, ForkAndPR]
