from urllib.parse import quote

import requests

from controller.auth_token import refresh_firebase_id_token
from controller.user_session import UserSession
from modal.constants import Constants


class SupabaseStorageClient:
    """Small authenticated wrapper around the Supabase Storage HTTP API."""

    def __init__(self, session: UserSession | None = None):
        self.session = session or UserSession()

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        if not Constants.SUPABASE_PUBLISHABLE_KEY:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY is not configured")
        if not self.session.id_token:
            raise RuntimeError("A Firebase login is required")

        headers = {
            "apikey": Constants.SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {self.session.id_token}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def _object_url(bucket: str, path: str, authenticated: bool = False) -> str:
        route = "authenticated/" if authenticated else ""
        return (
            f"{Constants.SUPABASE_URL}/storage/v1/object/{route}"
            f"{quote(bucket, safe='')}/{quote(path, safe='/')}"
        )

    def authenticated_url(self, bucket: str, path: str) -> str:
        return self._object_url(bucket, path, authenticated=True)

    def _request(self, method: str, url: str, content_type=None, **kwargs):
        kwargs["headers"] = self._headers(content_type)
        kwargs.setdefault("timeout", (5, 30))
        response = requests.request(method, url, **kwargs)
        if response.status_code == 401 and refresh_firebase_id_token(self.session):
            kwargs["headers"] = self._headers(content_type)
            response = requests.request(method, url, **kwargs)
        return response

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> str:
        response = self._request(
            "POST", self._object_url(bucket, path), data=data, content_type=content_type
        )
        response.raise_for_status()
        return path

    def download(self, bucket: str, path: str):
        response = self._request(
            "GET", self._object_url(bucket, path, authenticated=True)
        )
        response.raise_for_status()
        return response

    def delete(self, bucket: str, paths: list[str]) -> bool:
        response = self._request(
            "DELETE",
            f"{Constants.SUPABASE_URL}/storage/v1/object/{quote(bucket, safe='')}",
            json={"prefixes": paths},
            content_type="application/json",
        )
        response.raise_for_status()
        return True
