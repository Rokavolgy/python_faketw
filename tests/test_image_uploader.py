import unittest
from unittest.mock import patch, MagicMock
import io

from controller.image_uploader import ImageUploader


class TestImageUploader(unittest.TestCase):
    def setUp(self):
        self.image_uploader = ImageUploader()

    def test_get_file_url(self):
        """ file URL generation"""
        filename = "test_image.jpg"
        expected_url = self.image_uploader.STORAGE_URL + filename
        self.assertEqual(self.image_uploader.get_file_url(filename), expected_url)

    @patch('PIL.Image.open')
    def test_compress_image_below_max_size(self, mock_image_open):
        """when the image is already below max size"""

        mock_img = MagicMock()
        mock_img.width = 800
        mock_img.height = 600
        mock_img.save.side_effect = lambda output, format, quality, optimize: output.write(
            b'x' * 400000)
        mock_image_open.return_value = mock_img

        result = self.image_uploader.compress_image("fake_image.jpg")

        self.assertIsInstance(result, io.BytesIO)
        mock_img.save.assert_called()

    @patch('PIL.Image.open')
    def test_compress_image_above_max_size(self, mock_image_open):
        """when the image is above max size"""

        mock_img = MagicMock()
        mock_img.width = 1500
        mock_img.height = 1200


        def save_effect(output, format, quality, optimize):
            if quality > 90:
                output.write(b'x' * 1000000)
            else:
                output.write(b'x' * 400000)

        mock_img.save.side_effect = save_effect
        mock_image_open.return_value = mock_img

        result = self.image_uploader.compress_image("fake_image.jpg")

        self.assertIsInstance(result, io.BytesIO)
        self.assertTrue(mock_img.save.call_count > 1)


if __name__ == '__main__':
    unittest.main()
