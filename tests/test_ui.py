import unittest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
import sys

from post_widget import PostWidget, ClickableLabel
from modal.post import PostData
#potentially broken

class TestUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.post_data = MagicMock(spec=PostData)
        self.post_data.id = "test_id"
        self.post_data.userId = "user123"
        self.post_data.userName = "Test User"
        self.post_data.content = "Test content"
        self.post_data.timestamp = None
        self.post_data.userProfilePicUrl = None
        self.post_data.mediaUrls = []
        self.post_data.likesCount = 5
        self.post_data.commentsCount = 2
        self.post_data.likedByCurrentUser = False

        with patch('controller.image_loader_task.ImageLoaderTask'):
            self.post_widget = PostWidget(self.post_data)

    def test_clickable_label_emits_signal(self):
        """ClickableLabel emits clicked signal when clicked"""
        label = ClickableLabel("user123")

        signal_emitted = False
        emitted_id = None

        def slot(user_id):
            nonlocal signal_emitted, emitted_id
            signal_emitted = True
            emitted_id = user_id

        label.clicked.connect(slot)

        QTest.mouseClick(label, Qt.LeftButton)

        self.assertTrue(signal_emitted)
        self.assertEqual(emitted_id, "user123")

    def test_post_widget_displays_content(self):
        """PostWidget correctly displays the post content"""
        self.assertEqual(self.post_widget.content_label.text(), "Test content")
        self.assertEqual(self.post_widget.username_label.text(), "Test User")

        self.assertEqual(self.post_widget.like_button.text().strip(), "5")


if __name__ == '__main__':
    unittest.main()
