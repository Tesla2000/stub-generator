from enum import StrEnum, auto


class InputType(StrEnum):
    STUB_GENERATOR = auto()
    EXISTING_STUBS = auto()
