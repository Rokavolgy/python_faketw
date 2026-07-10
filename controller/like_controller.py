import logging
from datetime import datetime

from google.cloud import firestore
from google.cloud.firestore import Increment

from controller.firebase_client import get_db

logger = logging.getLogger(__name__)


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


def like_post(post_id, user_id):
    try:
        post_ref = get_db().collection("posts").document(post_id)
        post_doc = post_ref.get()

        if not post_doc.exists:
            logger.warning("Post %s not found while liking", post_id)
            return False

        like_doc_ref = post_ref.collection("likes").document(user_id)
        if like_doc_ref.get().exists:
            logger.debug("User %s already liked post %s", user_id, post_id)
            return True

        like_data = {"userId": user_id, "postId": post_id, "timestamp": datetime.now()}
        like_doc_ref.set(like_data)
        post_ref.update({"likesCount": Increment(1)})
        return True
    except Exception as e:
        logger.exception("Error liking post %s", post_id)
        return False


def unlike_post(post_id, user_id):
    try:
        post_ref = get_db().collection("posts").document(post_id)
        post_doc = post_ref.get()

        if not post_doc.exists:
            logger.warning("Post %s not found while unliking", post_id)
            return False

        like_doc_ref = post_ref.collection("likes").document(user_id)
        if not like_doc_ref.get().exists:
            logger.debug("User %s has not liked post %s", user_id, post_id)
            return True

        like_doc_ref.delete()
        post_ref.update({"likesCount": Increment(-1)})
        return True
    except Exception as e:
        logger.exception("Error unliking post %s", post_id)
        return False


def toggle_post_like(post_id, user_id):
    if not user_id:
        logger.warning("Unauthenticated like toggle requested")
        return False

    try:
        post_ref = get_db().collection("posts").document(post_id)
        like_doc_ref = post_ref.collection("likes").document(user_id)

        if like_doc_ref.get().exists:
            return unlike_post(post_id, user_id)
    except Exception as e:
        logger.exception("Error toggling like for post %s", post_id)
        return False
