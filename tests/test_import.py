from unittest import TestCase


class TestImport(TestCase):
    @staticmethod
    def test_import():
        import stub_generator  # ignore

        _ = stub_generator
