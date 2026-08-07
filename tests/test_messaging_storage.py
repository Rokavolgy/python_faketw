import unittest
from unittest.mock import MagicMock, patch

from controller.messaging_controller import direct_conversation_id, send_text_message
from controller.supabase_storage_client import SupabaseStorageClient
from controller.user_session import UserSession
from modal.constants import Constants


class MessagingControllerTests(unittest.TestCase):
    def setUp(self):
        UserSession._instance = None
        UserSession().set_auth_data("user-a", "firebase-token", "refresh-token")

    def tearDown(self):
        UserSession._instance = None

    def test_direct_conversation_id_is_order_independent(self):
        self.assertEqual(
            direct_conversation_id("user-a", "user-b"),
            direct_conversation_id("user-b", "user-a"),
        )

    @patch("controller.messaging_controller.get_db")
    def test_text_send_uses_one_batch(self, get_db):
        database = MagicMock()
        get_db.return_value = database

        message_id = send_text_message("conversation-1", " hello ")

        self.assertTrue(message_id)
        batch = database.batch.return_value
        batch.set.assert_called_once()
        batch.update.assert_called_once()
        batch.commit.assert_called_once()
        message = batch.set.call_args.args[1]
        self.assertEqual(message["senderId"], "user-a")
        self.assertEqual(message["text"], "hello")
        self.assertEqual(message["type"], "text")


class SupabaseStorageClientTests(unittest.TestCase):
    def setUp(self):
        UserSession._instance = None
        self.session = UserSession()
        self.session.set_auth_data("user-a", "firebase-token", "refresh-token")

    def tearDown(self):
        UserSession._instance = None

    @patch("controller.supabase_storage_client.requests.request")
    def test_upload_forwards_firebase_token(self, request):
        response = MagicMock(status_code=200)
        request.return_value = response
        with patch.object(Constants, "SUPABASE_PUBLISHABLE_KEY", "publishable-key"):
            path = SupabaseStorageClient(self.session).upload(
                "faktw2", "post-images/user-a/image.webp", b"image", "image/webp"
            )

        self.assertEqual(path, "post-images/user-a/image.webp")
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer firebase-token")
        self.assertEqual(headers["apikey"], "publishable-key")
        self.assertEqual(headers["Content-Type"], "image/webp")

    def test_missing_publishable_key_fails_closed(self):
        with patch.object(Constants, "SUPABASE_PUBLISHABLE_KEY", ""):
            with self.assertRaises(RuntimeError):
                SupabaseStorageClient(self.session).upload(
                    "faktw2", "image.webp", b"image", "image/webp"
                )


if __name__ == "__main__":
    unittest.main()
