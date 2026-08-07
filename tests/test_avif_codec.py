import unittest

from widgets.avif_widget import avif_codec_self_test


class TestAvifCodec(unittest.TestCase):
    def test_pillow_avif_round_trip(self):
        self.assertTrue(avif_codec_self_test())


if __name__ == "__main__":
    unittest.main()
