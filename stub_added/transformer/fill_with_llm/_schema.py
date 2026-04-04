from pathlib import Path
from typing import Annotated
from typing import Self

from pydantic import AfterValidator
from pydantic import BaseModel
from stub_added.transformer.stub_postprocessor import postprocess_stub


class _StubOutput(BaseModel):
    stub_path: str
    stub_contents: Annotated[str, AfterValidator(postprocess_stub)]


class _StubOutputPath(BaseModel):
    stub_path: Path
    stub_contents: Annotated[str, AfterValidator(postprocess_stub)]

    @classmethod
    def from_stub_output(cls, stub_output: _StubOutput) -> Self:
        return cls(
            stub_path=Path(stub_output.stub_path),
            stub_contents=stub_output.stub_contents,
        )


class _OutputSchema(BaseModel):
    stub_outputs: list[_StubOutput]


_STUB_RULES = (
    "Important: Remove unused imports and add missing imports. "
    "Remember that Forward reference only works with Union, not with | operator. "
    "Add imports from other packages if they are required. "
    "Type hints you add must be compatible with mypy --strict formula so include missing type "
    "parameters from generics. All args, kwargs and return of the function should have a type "
    "hint (except self and cls) in some instances. "
    "For classes that inherit from a generic dict, define TypeVars and use them consistently "
    "in both the class definition and all overridden methods. The key TypeVar must be bound to "
    "Hashable. Example: "
    '\'_Key = TypeVar("_Key", bound=Hashable); _Value = TypeVar("_Value"); '
    "class LRUCache(dict[_Key, _Value]): "
    "    def __getitem__(self, key: _Key) -> _Value: ... "
    "    def __setitem__(self, key: _Key, value: _Value) -> None: ... "
    "    def popitem(self) -> tuple[_Key, _Value]: ...' "
    "Always type *args as *args: Any and **kwargs as **kwargs: Any. "
    "Never use object as a type annotation — replace every : object with : Any. "
    "When mypy reports a Liskov substitution principle violation on an overridden method, "
    "read the error carefully — it tells you the exact type the supertype defines. "
    "Use that type verbatim in the override."
)
