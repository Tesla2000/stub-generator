from unittest import TestCase


class TestImport(TestCase):
    @staticmethod
    def test_import():
        import stub_added  # ignore

        _ = stub_added
