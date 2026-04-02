import tempfile
from pathlib import Path
from unittest import TestCase

from pydantic import HttpUrl
from stub_added.input.stub_generator import StubGenerator
from stub_added.transformer.fill_with_llm import FillWithLLM


class TestIntegrationGoogleAuth(TestCase):
    def test_stubs_generated_and_topo_ordered(self):
        google_auth_url = HttpUrl(
            "https://github.com/googleapis/google-auth-library-python.git"
        )
        with tempfile.TemporaryDirectory() as tmp:
            stub_generator = StubGenerator(
                stubbed_repo_url=google_auth_url, paths=[Path("google")]
            )
            stub_tuples = tuple(stub_generator.generate(Path(tmp)))
            layers = tuple(FillWithLLM._topo_layers(stub_tuples))

        self.assertGreater(len(layers), 1)
        self.assertLess(max(map(len, layers)), 21)
