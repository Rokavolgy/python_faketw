import unittest
from unittest.mock import MagicMock, patch

import requests

from controller.like_controller import LikeUpdateResult, set_post_like
from controller.user_session import UserSession
from modal.constants import Constants


class TestLikeController(unittest.TestCase):
    def setUp(self):
        self.user_session = UserSession()
        self.user_session.set_auth_data("firebase-user", "firebase-token", "refresh-token")

    def tearDown(self):
        self.user_session.clear_session()

    @patch("controller.like_controller.requests.post")
    def test_set_post_like_sends_only_desired_state(self, post):
        response = MagicMock()
        response.json.return_value = {"liked": True, "likesCount": 8}
        post.return_value = response

        result = set_post_like("post-123", True)

        self.assertEqual(result, LikeUpdateResult(liked=True, likes_count=8))
        post.assert_called_once_with(
            Constants.LIKE_URL,
            headers={
                "Authorization": "Bearer firebase-token",
                "Content-Type": "application/json",
            },
            json={"postId": "post-123", "liked": True},
            timeout=(5, 20),
        )
        sent_body = post.call_args.kwargs["json"]
        self.assertNotIn("userId", sent_body)
        self.assertNotIn("likesCount", sent_body)

    @patch("controller.like_controller.requests.post")
    def test_invalid_server_response_fails_closed(self, post):
        response = MagicMock()
        response.json.return_value = {"liked": True, "likesCount": "8"}
        post.return_value = response

        self.assertIsNone(set_post_like("post-123", True))

    @patch("controller.like_controller.requests.post")
    def test_timeout_is_retried_once(self, post):
        success = MagicMock(status_code=200)
        success.json.return_value = {"liked": True, "likesCount": 8}
        post.side_effect = [requests.ReadTimeout("cold start"), success]

        result = set_post_like("post-123", True)

        self.assertEqual(result, LikeUpdateResult(liked=True, likes_count=8))
        self.assertEqual(post.call_count, 2)

    @patch("controller.like_controller.requests.post")
    def test_expired_id_token_is_refreshed_once(self, post):
        unauthorized = MagicMock(status_code=401)
        refreshed = MagicMock(status_code=200)
        refreshed.json.return_value = {
            "id_token": "fresh-token",
            "refresh_token": "fresh-refresh-token",
            "user_id": "firebase-user",
        }
        success = MagicMock(status_code=200)
        success.json.return_value = {"liked": False, "likesCount": 7}
        post.side_effect = [unauthorized, refreshed, success]

        result = set_post_like("post-123", False)

        self.assertEqual(result, LikeUpdateResult(liked=False, likes_count=7))
        self.assertEqual(self.user_session.id_token, "fresh-token")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            post.call_args_list[-1].kwargs["headers"]["Authorization"],
            "Bearer fresh-token",
        )

    @patch("controller.like_controller.requests.post")
    def test_unauthenticated_request_does_not_call_function(self, post):
        self.user_session.clear_session()

        self.assertIsNone(set_post_like("post-123", True))
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
