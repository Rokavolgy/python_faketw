import logging

logger = logging.getLogger(__name__)

FIREBASE_REST_API = "https://identitytoolkit.googleapis.com/v1/accounts"
PROJECT_ID = "mobilapp-7c1e5"
API_KEY = "AIzaSyDkd5bMZ3frFvxNl39FayzWIfT3afNlJ4s"

db = None
user_info_cache = {}


def set_db(client):
    global db
    db = client


def get_db():
    if db is None:
        raise RuntimeError("Firestore client is not initialized")
    return db


def fetch_user_info(user_id):
    if user_id in user_info_cache:
        return user_info_cache[user_id]

    doc_ref = get_db().collection("userdata").document(user_id)
    doc = doc_ref.get()
    if doc.exists:
        user_data = doc.to_dict()
        user_info_cache[user_id] = user_data
        return user_data
    return None


def clear_cache():
    user_info_cache.clear()
    logger.debug("User information cache cleared")
