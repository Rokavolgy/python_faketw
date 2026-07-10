import logging
import uuid

from google.cloud.firestore import Increment
from google.cloud.firestore_v1 import Query, SERVER_TIMESTAMP

from controller.firebase_client import get_db
from modal.comment import CommentData

logger = logging.getLogger(__name__)


def fetch_post_comments(post_id, limit=100):
    try:
        comments_ref = get_db().collection("posts").document(post_id).collection(
            "comments"
        ).order_by(
            field_path="timestamp", direction=Query.ASCENDING
        ).limit(limit)

        comments = []
        for doc in comments_ref.stream():
            comment_dict = doc.to_dict()
            comment_dict["id"] = doc.id
            comments.append(CommentData.from_dict(comment_dict))
        return comments
    except Exception as e:
        logger.exception("Error fetching comments for post %s", post_id)
        return []


def add_comment(post_id, user_id, user_name, user_profile_pic_url, content):
    try:
        comment_id = str(uuid.uuid4())
        comment_ref = get_db().collection("posts").document(post_id).collection(
            "comments"
        ).document(comment_id)

        comment = CommentData(
            id=comment_id,
            postId=post_id,
            userId=user_id,
            userName=user_name,
            userProfilePicUrl=user_profile_pic_url,
            content=content,
            timestamp=SERVER_TIMESTAMP,
        )

        comment_ref.set(CommentData.to_dict(comment))
        get_db().collection("posts").document(post_id).update(
            {"commentsCount": Increment(1)}
        )
        return True
    except Exception as e:
        logger.exception("Error adding comment to post %s", post_id)
        return False


def delete_comment(post_id, comment_id, requesting_user_id):
    """Delete a comment owned by the requesting user and update the post count."""
    if not post_id or not comment_id or not requesting_user_id:
        return False

    try:
        database = get_db()
        post_ref = database.collection("posts").document(post_id)
        comment_ref = post_ref.collection("comments").document(comment_id)
        comment_snapshot = comment_ref.get()
        if not comment_snapshot.exists:
            return False
        if comment_snapshot.to_dict().get("userId") != requesting_user_id:
            return False

        post_snapshot = post_ref.get()
        if not post_snapshot.exists:
            return False
        comments_count = post_snapshot.to_dict().get("commentsCount", 0) or 0

        comment_option = database.write_option(
            last_update_time=comment_snapshot.update_time
        )
        post_option = database.write_option(last_update_time=post_snapshot.update_time)
        batch = database.batch()
        batch.delete(comment_ref, option=comment_option)
        batch.update(
            post_ref,
            {"commentsCount": max(0, comments_count - 1)},
            option=post_option,
        )
        batch.commit()
        return True
    except Exception as e:
        logger.exception("Error deleting comment %s", comment_id)
        return False
