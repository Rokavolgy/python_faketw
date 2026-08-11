import json
import logging

import requests
from google.cloud.firestore import Client
from google.oauth2.credentials import Credentials
from requests.exceptions import HTTPError

from controller.firebase_client import API_KEY, FIREBASE_REST_API, PROJECT_ID, fetch_user_info, set_db
from controller.user_controller import create_user_profile, default_profile_for_user
from controller.user_session import UserSession
from modal.user import ProfileData

logger = logging.getLogger(__name__)
AUTH_REQUEST_TIMEOUT = (5, 20)


def sign_in_with_email_and_password(api_key, email, password):
    request_url = "%s:signInWithPassword?key=%s" % (FIREBASE_REST_API, api_key)
    headers = {"content-type": "application/json; charset=UTF-8"}
    data = json.dumps({"email": email, "password": password, "returnSecureToken": True})

    req = requests.post(
        request_url,
        headers=headers,
        data=data,
        timeout=AUTH_REQUEST_TIMEOUT,
    )

    try:
        req.raise_for_status()
    except HTTPError as error:
        raise HTTPError(f"{error}: {req.text}", response=req) from error

    return req.json()


def register_user(email, password):
    try:
        request_url = "%s:signUp?key=%s" % (FIREBASE_REST_API, API_KEY)
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})

        req = requests.post(
            request_url,
            headers=headers,
            data=data,
            timeout=AUTH_REQUEST_TIMEOUT,
        )
        req.raise_for_status()
        response = req.json()

        user_session = UserSession()
        user_session.set_auth_data(
            user_id=response.get("localId"),
            id_token=response.get("idToken"),
            refresh_token=response.get("refreshToken"),
        )
        creds = Credentials(response["idToken"], response["refreshToken"])
        set_db(Client(PROJECT_ID, creds))

        return True, response
    except Exception:
        logger.exception("Registration failed")
        return False, None


def login_user(email, password):
    response = None
    try:
        response = sign_in_with_email_and_password(API_KEY, email, password)
        user_session = UserSession()
        user_session.set_auth_data(
            user_id=response.get("localId"),
            id_token=response.get("idToken"),
            refresh_token=response.get("refreshToken"),
        )
        creds = Credentials(response["idToken"], response["refreshToken"])
        set_db(Client(PROJECT_ID, creds))

        user_info = fetch_user_info(user_session.user_id)
        if user_info:
            profile_data = ProfileData.from_dict(user_info)
            user_session.set_profile_data(profile_data)
        else:
            logger.info("No profile found for %s; creating defaults", user_session.user_id)
            default_profile = default_profile_for_user(
                user_session.user_id, email, ProfileData
            )
            user_session.set_profile_data(default_profile)
            if not create_user_profile(user_session.user_id, default_profile):
                raise RuntimeError("Unable to create the default user profile")
        logger.debug("User profile loaded.")
        return True, response
    except (TypeError, RuntimeError, HTTPError) as e:
        logger.exception("Login failed")
        return False, response
