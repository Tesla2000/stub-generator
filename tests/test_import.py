from unittest import TestCase


class TestImport(TestCase):
    @staticmethod
    def test_import():
        import stub_adder  # ignore

        _ = stub_adder
