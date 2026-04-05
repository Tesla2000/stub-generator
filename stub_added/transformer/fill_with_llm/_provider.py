from enum import auto
from enum import StrEnum
from typing import Any
from typing import Optional


class Provider(StrEnum):
    GEMINI = auto()
    OPENAI = auto()


def get_provider(value: Any) -> Optional[Provider]:
    if isinstance(value, dict) and "type" in value:
        return Provider(value["type"])
    if hasattr(value, "type"):  # ignore
        return Provider(value.type)
    if isinstance(value, dict):
        model = value.get("model", "")
    elif hasattr(value, "model"):  # ignore
        model = value.model
    else:
        return None
    return Provider.OPENAI if str(model).startswith("gpt") else Provider.GEMINI
