import logging

import requests
from google.cloud.firestore import Client
from google.oauth2.credentials import Credentials

from controller.firebase_client import API_KEY, PROJECT_ID, set_db
from controller.user_session import UserSession

logger = logging.getLogger(__name__)


def refresh_firebase_id_token(user_session: UserSession | None = None) -> bool:
    """Refresh the current Firebase ID token in-place."""
    user_session = user_session or UserSession()
    if not user_session.refresh_token:
        return False

    try:
        response = requests.post(
            f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": user_session.refresh_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        id_token = result.get("id_token")
        refresh_token = result.get("refresh_token")
        if not isinstance(id_token, str) or not isinstance(refresh_token, str):
            raise ValueError("Invalid Firebase token refresh response")

        user_session.set_auth_data(
            user_id=result.get("user_id") or user_session.user_id,
            id_token=id_token,
            refresh_token=refresh_token,
        )
        set_db(Client(PROJECT_ID, Credentials(id_token, refresh_token)))
        return True
    except (requests.RequestException, ValueError, TypeError):
        logger.exception("Unable to refresh Firebase ID token")
        return False
