from pathlib import Path
from typing import Annotated
from typing import Self

from pydantic import AfterValidator
from pydantic import BaseModel

from stub_adder.transformer.stub_postprocessor import postprocess_stub


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
    "Remember that Forward references only work with Union, not with the | operator. "
    "Add imports from other packages if they are required. "
    "Type hints you add must be compatible with mypy --strict, so include missing type "
    "parameters from generics. All args, kwargs, and return values of functions should have "
    "type hints (except self and cls). "
    "For classes that inherit from a generic dict, define TypeVars and use them consistently "
    "in both the class definition and all overridden methods. The key TypeVar must be bound to "
    "Hashable. Example: "
    '\'_Key = TypeVar("_Key", bound=Hashable); _Value = TypeVar("_Value"); '
    "class LRUCache(dict[_Key, _Value]): "
    "    def __getitem__(self, key: _Key) -> _Value: ... "
    "    def __setitem__(self, key: _Key, value: _Value) -> None: ... "
    "    def popitem(self) -> tuple[_Key, _Value]: ...' "
    "When a subclass overrides a method that uses @overload in the superclass, you must "
    "repeat all @overload variants in the subclass stub. Do not include an implementation "
    "overload (the bare def without @overload) in a stub file — stubs only contain the "
    "@overload decorated signatures. "
    "When stubtest reports 'stub parameter X should be positional or keyword (remove \"/\")' "
    "it means the runtime method does not use positional-only parameters, but the stub "
    "inherited a positional-only signature (with '/') from the superclass. "
    "Fix it by overriding the method explicitly in the subclass stub without '/' in the "
    "parameter list. Use @overload if the superclass method is overloaded. "
    "Never copy '/' from superclass stubs when the runtime method is plain Python without '/'. "
    "In stub files (.pyi), never use '# type: ignore[override]' on @overload definitions — "
    "it will be reported as an unused ignore. Overload sets in stubs do not need it. "
    "In stub files, always use '= ...' for default parameter values, never the actual "
    "default value (e.g. 'default: None = ...' not 'default: None = None'). "
    "Always type *args as *args: Any and **kwargs as **kwargs: Any. "
    "Never use object as a type annotation — replace every ': object' with ': Any'. "
    "When mypy reports a Liskov substitution principle violation on an overridden method, "
    "read the error carefully — it tells you the exact type the supertype defines. "
    "Use that type verbatim in the override. "
    "Use object instead of Any where possible. "
    "Use MutableMapping instead of dict and MutableSequence instead of list wherever possible."
)
