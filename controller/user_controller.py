import logging

from google.cloud.firestore_v1 import DELETE_FIELD, SERVER_TIMESTAMP

from controller.firebase_client import get_db

logger = logging.getLogger(__name__)


def update_user_profile(user_id, profile_data):
    try:
        user_ref = get_db().collection("userdata").document(user_id)
        public_profile = profile_data.to_dict_without_id(profile_data)
        public_profile.update({"email": DELETE_FIELD, "userId": DELETE_FIELD})
        user_ref.set(public_profile, merge=True)
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
    email_prefix = email.split("@", 1)[0]
    username = "".join(
        character
        for character in email_prefix
        if character.isascii() and (character.isalnum() or character == "_")
    )[:40]
    if len(username) < 3:
        username = f"user_{user_id[:8]}"[:40]
    display_name = email_prefix[:40]
    if len(display_name) < 3:
        display_name = "New User"
    return profile_cls(
        id=user_id,
        displayName=display_name,
        bio="",
        profileImageUrl="",
        coverImageUrl="",
        website="",
        location="",
        dateOfBirth=__import__("datetime").datetime(2000, 1, 1),
        createdAt=SERVER_TIMESTAMP,
        username=username,
    )
