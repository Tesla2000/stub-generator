from pathlib import Path
from typing import NamedTuple


class _StubTuple(NamedTuple):
    py_path: Path
    pyi_path: Path
