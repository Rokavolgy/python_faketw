import logging

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from controller.firebase_client import get_db

logger = logging.getLogger(__name__)


def update_user_profile(user_id, profile_data):
    try:
        user_ref = get_db().collection("userdata").document(user_id)
        user_ref.set(profile_data.to_dict_without_id(profile_data), merge=True)
        return True
    except Exception as e:
        logger.exception("Error updating user profile for %s", user_id)
        return False


def create_user_profile(user_id, profile_data):
    try:
        user_ref = get_db().collection("userdata").document(user_id)
        user_ref.set(profile_data.to_dict_without_id(profile_data), merge=True)
        return True
    except Exception as e:
        logger.exception("Error creating user profile for %s", user_id)
        return False


def default_profile_for_user(user_id, email, profile_cls):
    return profile_cls(
        id=user_id,
        displayName=email.split("@")[0],
        bio="",
        profileImageUrl="",
        coverImageUrl="",
        website="",
        location="",
        dateOfBirth=__import__("datetime").datetime(2000, 1, 1),
        createdAt=SERVER_TIMESTAMP,
        username=email.split("@")[0],
    )
