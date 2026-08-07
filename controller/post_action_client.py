import logging

import requests

from controller.auth_token import refresh_firebase_id_token
from controller.user_session import UserSession
from modal.constants import Constants

logger = logging.getLogger(__name__)


def _send(payload: dict, id_token: str):
    return requests.post(
        Constants.POST_ACTIONS_URL,
        headers={
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(5, 25),
    )


def send_post_action(payload: dict, session: UserSession | None = None):
    session = session or UserSession()
    if not session.is_authenticated or not session.id_token:
        logger.warning("Unauthenticated post action requested")
        return None

    try:
        response = _send(payload, session.id_token)
        if response.status_code == 401 and refresh_firebase_id_token(session):
            response = _send(payload, session.id_token)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Invalid post action response")
        return result
    except (requests.RequestException, ValueError, TypeError):
        logger.exception("Post action failed: %s", payload.get("action"))
        return None
