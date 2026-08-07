import logging

from google.cloud import firestore
from google.cloud.firestore_v1 import Query, SERVER_TIMESTAMP

from controller.firebase_client import fetch_user_info, get_db
from controller.like_controller import fetch_user_likes
from controller.post_action_client import send_post_action
from controller.supabase_storage_client import SupabaseStorageClient
from controller.user_session import UserSession
from modal import post
from modal.constants import Constants
from modal.user import ProfileData

logger = logging.getLogger(__name__)


@firestore.transactional
def _commit_new_post(transaction, post_ref, rate_limit_ref, post_dict):
    rate_limit_ref.get(transaction=transaction)
    transaction.set(post_ref, post_dict)
    transaction.set(
        rate_limit_ref,
        {
            "lastPostAt": SERVER_TIMESTAMP,
            "lastPostId": post_dict["id"],
        },
    )


def fetch_posts():
    doc_ref = get_db().collection("posts").order_by(
        field_path="timestamp", direction=Query.DESCENDING
    )
    return doc_ref.stream()


def post_data_from_document(post_doc, user_likes=None):
    post_dict = post_doc.to_dict()
    post_dict["id"] = post_doc.id
    post_data = post.PostData.from_dict(post_dict)
    user_data = fetch_user_info(post_data.userId)

    if user_data:
        user = ProfileData.from_dict(user_data)
        post_data.userName = user.displayName
        post_data.userProfilePicUrl = user.profileImageUrl
        post_data.userData = user

    if user_likes and post_data.id in user_likes:
        post_data.likedByCurrentUser = True

    return post_data


def fetch_posts_page(before_timestamp=None, limit=20, user_likes=None):
    try:
        query = get_db().collection("posts")
        if before_timestamp:
            query = query.where(
                filter=firestore.FieldFilter("timestamp", "<", before_timestamp)
            )
        query = query.order_by(
            field_path="timestamp", direction=Query.DESCENDING
        ).limit(limit)

        return [
            post_data_from_document(post_doc, user_likes=user_likes)
            for post_doc in query.stream()
        ]
    except Exception as e:
        logger.exception("Error fetching posts page")
        return []


def fetch_user_posts(user_id, limit=None):
    doc_ref = get_db().collection("posts").where(
        filter=firestore.FieldFilter("userId", "==", user_id)
    ).order_by(
        field_path="timestamp", direction=Query.DESCENDING
    )
    if limit:
        doc_ref = doc_ref.limit(limit)
    return doc_ref.stream()


def fetch_posts_and_user_info(userId=None, limit=None, current_user_id=None, user_likes=None):
    if userId:
        posts = fetch_user_posts(userId, limit=limit)
    else:
        posts = fetch_posts()

    if user_likes is None:
        user_likes = fetch_user_likes(current_user_id) if current_user_id else []

    return [
        post_data_from_document(post_doc, user_likes=user_likes)
        for post_doc in posts
    ]


def fetch_post_by_id(post_id, user_likes=None):
    try:
        post_ref = get_db().collection("posts").document(post_id)
        post_doc = post_ref.get()

        if not post_doc.exists:
            logger.warning("Post %s not found", post_id)
            return None

        return post_data_from_document(post_doc, user_likes=user_likes)
    except Exception as e:
        logger.exception("Error fetching post %s", post_id)
        return None


def create_new_post(post_data):
    try:
        post_dict = post_data.to_dict(post_data)
        database = get_db()
        post_ref = database.collection("posts").document(post_dict["id"])
        rate_limit_ref = database.collection("postRateLimits").document(
            post_dict["userId"]
        )
        _commit_new_post(
            database.transaction(), post_ref, rate_limit_ref, post_dict
        )
        return True
    except Exception as e:
        logger.exception("Error creating post")
        return False


def delete_post(post_id):
    result = send_post_action({"action": "deletePost", "postId": post_id})
    if not result or not result.get("deleted"):
        return False

    media_urls = result.get("mediaUrls")
    if isinstance(media_urls, list):
        expected_prefix = f"post-images/{UserSession().user_id}/"
        owned_paths = [
            path
            for path in media_urls
            if isinstance(path, str)
               and path.startswith(expected_prefix)
               and path.lower().endswith((".webp", ".avif"))
        ]
        if owned_paths:
            try:
                SupabaseStorageClient().delete(Constants.PUBLIC_IMAGE_BUCKET, owned_paths)
            except Exception:
                logger.exception("Unable to clean up media for deleted post %s", post_id)
    return True
