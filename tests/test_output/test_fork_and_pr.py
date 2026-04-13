import os
import tempfile
from pathlib import Path

import pytest
from pydantic import SecretStr

from stub_adder._stub_tuple import _StubTuple
from stub_adder.output.fork_and_pr import ForkAndPR


@pytest.mark.skipif(
    not os.getenv("RUN_MANUAL"), reason="Manual test — set RUN_MANUAL to run"
)
def test_push_to_fork() -> None:
    with tempfile.TemporaryDirectory() as stubs_root_str:
        stubs_root = Path(stubs_root_str)
        dummy = stubs_root / "pyphen" / "__init__.pyi"
        dummy.parent.mkdir(parents=True, exist_ok=True)
        dummy.write_text("")

        output = ForkAndPR(
            repo_name="Kozea/Pyphen",
            github_token=SecretStr(os.environ["GITHUB_TOKEN"]),
        )
        fork = None
        try:
            fork = output.save([_StubTuple(dummy, dummy)], stubs_root)
            fork = output.save([_StubTuple(dummy, dummy)], stubs_root)
        finally:
            if fork:
                fork.delete()
