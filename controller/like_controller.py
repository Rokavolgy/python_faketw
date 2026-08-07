import logging
from dataclasses import dataclass

import requests
from google.cloud import firestore

from controller.auth_token import refresh_firebase_id_token
from controller.firebase_client import get_db
from controller.user_session import UserSession
from modal.constants import Constants

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LikeUpdateResult:
    liked: bool
    likes_count: int


def _send_like_request(post_id: str, liked: bool, id_token: str):
    return requests.post(
        Constants.LIKE_URL,
        headers={
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json",
        },
        json={"postId": post_id, "liked": liked},
        timeout=(5, 20),
    )


def _send_like_request_with_retry(post_id: str, liked: bool, id_token: str):
    try:
        return _send_like_request(post_id, liked, id_token)
    except (requests.Timeout, requests.ConnectionError):
        # This endpoint sets a desired state rather than incrementing blindly,
        # so retrying after a lost/late response cannot double-like a post.
        logger.warning("Like request timed out; retrying once for post %s", post_id)
        return _send_like_request(post_id, liked, id_token)


def fetch_user_likes(user_id):
    try:
        doc_ref = get_db().collection_group("likes").where(
            filter=firestore.FieldFilter("userId", "==", user_id)
        )
        docs = doc_ref.stream()
        liked_posts = [doc.get("postId") for doc in docs]
        logger.debug("Loaded %d liked posts", len(liked_posts))
        return liked_posts
    except Exception as e:
        logger.exception("Error fetching likes for user %s", user_id)
        return []


def set_post_like(post_id: str, liked: bool):
    """Set the current user's desired like state through the Edge Function.

    The client deliberately sends neither a user ID nor a like count. The Edge
    Function derives the user from the Firebase ID token and computes the count
    in a Firestore transaction.
    """
    user_session = UserSession()
    if not user_session.is_authenticated or not user_session.id_token:
        logger.warning("Unauthenticated like update requested")
        return None

    try:
        response = _send_like_request_with_retry(post_id, liked, user_session.id_token)
        if response.status_code == 401 and refresh_firebase_id_token(user_session):
            response = _send_like_request_with_retry(
                post_id, liked, user_session.id_token
            )
        response.raise_for_status()
        result = response.json()

        if not isinstance(result, dict):
            raise ValueError("Invalid like response from Edge Function")

        authoritative_liked = result.get("liked")
        likes_count = result.get("likesCount")
        if (
                not isinstance(authoritative_liked, bool)
                or not isinstance(likes_count, int)
                or isinstance(likes_count, bool)
                or likes_count < 0
        ):
            raise ValueError("Invalid like response from Edge Function")

        return LikeUpdateResult(authoritative_liked, likes_count)
    except (requests.RequestException, ValueError, TypeError):
        logger.exception("Error updating like for post %s", post_id)
        return None
