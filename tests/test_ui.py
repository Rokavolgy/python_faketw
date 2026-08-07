import sys
import unittest
from unittest.mock import patch, MagicMock

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from controller.like_controller import LikeUpdateResult
from controller.user_session import UserSession
from modal.post import PostData
from widgets.clickable_labels import ClickableLabel
from widgets.post_widget import PostWidget


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
        self.assertEqual(self.post_widget.content_label.textFormat(), Qt.PlainText)
        self.assertEqual(self.post_widget.username_label.textFormat(), Qt.PlainText)

        self.assertEqual(self.post_widget.like_button.text().strip(), "5")

    def test_post_widget_can_be_rebound(self):
        rebound = MagicMock(spec=PostData)
        rebound.id = "second_id"
        rebound.userId = "second_user"
        rebound.userName = "Second User"
        rebound.content = "Reused widget content"
        rebound.timestamp = None
        rebound.userProfilePicUrl = None
        rebound.mediaUrls = []
        rebound.likesCount = 1
        rebound.commentsCount = 3
        rebound.likedByCurrentUser = True

        previous_generation = self.post_widget._binding_generation
        self.post_widget.bind_post(rebound)

        self.assertGreater(
            self.post_widget._binding_generation, previous_generation
        )
        self.assertEqual(self.post_widget.post_data.id, "second_id")
        self.assertEqual(
            self.post_widget.content_label.text(), "Reused widget content"
        )
        self.assertEqual(self.post_widget.profile_pic.userId, "second_user")

    def test_like_completion_uses_authoritative_server_count(self):
        user_session = UserSession()
        user_session.set_user_likes(["test_id"])
        self.post_widget._like_rollback = (False, 5, "test_id")
        self.post_widget._like_update_pending = True

        self.post_widget._on_toggle_finished(
            LikeUpdateResult(liked=True, likes_count=9)
        )

        self.assertTrue(self.post_widget.post_data.likedByCurrentUser)
        self.assertEqual(self.post_widget.post_data.likesCount, 9)
        self.assertEqual(self.post_widget.like_button.text().strip(), "9")


if __name__ == '__main__':
    unittest.main()
