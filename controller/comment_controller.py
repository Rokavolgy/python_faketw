import logging
import uuid

from google.cloud.firestore_v1 import Query

from controller.firebase_client import get_db
from controller.post_action_client import send_post_action
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


def add_comment(post_id, content):
    content = content.strip() if isinstance(content, str) else ""
    if not post_id or not content or len(content) > 4000:
        return False
    result = send_post_action(
        {
            "action": "createComment",
            "postId": post_id,
            "commentId": str(uuid.uuid4()),
            "content": content,
        }
    )
    return bool(result and result.get("created"))


def delete_comment(post_id, comment_id):
    """Delete the caller's comment through the trusted post-actions function."""
    if not post_id or not comment_id:
        return False
    result = send_post_action(
        {"action": "deleteComment", "postId": post_id, "commentId": comment_id}
    )
    return bool(result and result.get("deleted"))
