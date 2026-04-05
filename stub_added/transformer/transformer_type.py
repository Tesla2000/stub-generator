from enum import auto
from enum import StrEnum


class TransformerType(StrEnum):
    FILL_WITH_LLM = auto()
    NO_OP = auto()
