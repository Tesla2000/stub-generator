from abc import abstractmethod

from pydantic import BaseModel


class ManualFix(BaseModel):
    @abstractmethod
    def __call__(self, contents: str, errors: list[str]) -> str: ...
