import base64
import logging
import uuid

from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from controller.firebase_client import get_db
from controller.supabase_storage_client import SupabaseStorageClient
from controller.user_session import UserSession
from modal.constants import Constants

logger = logging.getLogger(__name__)


def _encode_uid(uid: str) -> str:
    return base64.urlsafe_b64encode(uid.encode("utf-8")).decode("ascii").rstrip("=")


def direct_conversation_id(first_user_id: str, second_user_id: str) -> str:
    first, second = sorted((first_user_id, second_user_id))
    return f"direct.{_encode_uid(first)}.{_encode_uid(second)}"


def ensure_direct_conversation(other_user_id: str) -> str:
    session = UserSession()
    if not session.user_id or not other_user_id or session.user_id == other_user_id:
        raise ValueError("A different signed-in user is required")

    conversation_id = direct_conversation_id(session.user_id, other_user_id)
    conversation_ref = get_db().collection("conversations").document(conversation_id)
    try:
        conversation_ref.create(
            {
                "type": "direct",
                "memberIds": sorted((session.user_id, other_user_id)),
                "createdAt": SERVER_TIMESTAMP,
                "updatedAt": SERVER_TIMESTAMP,
                "lastMessageId": "",
                "lastSenderId": "",
                "lastMessageType": "",
                "lastMessagePreview": "",
                "lastMessageAt": SERVER_TIMESTAMP,
            }
        )
    except AlreadyExists:
        pass
    return conversation_id


def _send_message(conversation_id: str, message: dict) -> str:
    session = UserSession()
    if not session.user_id:
        raise RuntimeError("A Firebase login is required")

    message_id = str(uuid.uuid4())
    database = get_db()
    conversation_ref = database.collection("conversations").document(conversation_id)
    message_ref = conversation_ref.collection("messages").document(message_id)
    message["senderId"] = session.user_id
    message["createdAt"] = SERVER_TIMESTAMP
    preview = message.get("text", "")[:80] if message["type"] == "text" else "Image"

    batch = database.batch()
    batch.set(message_ref, message)
    batch.update(
        conversation_ref,
        {
            "updatedAt": SERVER_TIMESTAMP,
            "lastMessageId": message_id,
            "lastSenderId": session.user_id,
            "lastMessageType": message["type"],
            "lastMessagePreview": preview,
            "lastMessageAt": SERVER_TIMESTAMP,
        },
    )
    batch.commit()
    return message_id


def send_text_message(conversation_id: str, text: str) -> str:
    text = text.strip()
    if not text or len(text) > 4000:
        raise ValueError("Messages must contain between 1 and 4000 characters")
    return _send_message(conversation_id, {"type": "text", "text": text})


def send_image_message(conversation_id: str, storage_path: str, caption: str = "") -> str:
    caption = caption.strip()
    if len(caption) > 2000:
        raise ValueError("Image captions cannot exceed 2000 characters")
    try:
        return _send_message(
            conversation_id,
            {
                "type": "image",
                "text": caption,
                "storageBucket": Constants.MESSAGE_IMAGE_BUCKET,
                "storagePath": storage_path,
            },
        )
    except Exception:
        try:
            SupabaseStorageClient().delete(Constants.MESSAGE_IMAGE_BUCKET, [storage_path])
        except Exception:
            logger.exception("Unable to clean up an unreferenced message image")
        raise


def mark_conversation_read(conversation_id: str, message_id: str = "") -> None:
    session = UserSession()
    if not session.user_id:
        return
    get_db().collection("conversations").document(conversation_id).collection(
        "readStates"
    ).document(session.user_id).set(
        {"lastReadAt": SERVER_TIMESTAMP, "lastReadMessageId": message_id}
    )
