import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

SCRIPT_PATH = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "tools"
        / "firebase_password.py"
)
SPEC = importlib.util.spec_from_file_location("firebase_password", SCRIPT_PATH)
firebase_password = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(firebase_password)


class FirebasePasswordTests(unittest.TestCase):
    def test_read_new_password_rejects_mismatch(self):
        with patch.object(
                firebase_password.getpass,
                "getpass",
                side_effect=["long-enough", "different"],
        ):
            with self.assertRaisesRegex(ValueError, "do not match"):
                firebase_password.read_new_password()

    def test_set_password_uses_resolved_uid(self):
        auth = MagicMock()
        app = object()
        existing_user = SimpleNamespace(uid="uid-123", email="person@example.com")
        updated_user = SimpleNamespace(uid="uid-123", email="person@example.com")
        auth.get_user_by_email.return_value = existing_user
        auth.update_user.return_value = updated_user
        args = SimpleNamespace(
            service_account=Path("key.json"),
            project=None,
            uid=None,
            email="person@example.com",
            yes=True,
        )

        with patch.object(
                firebase_password, "initialize_auth", return_value=(auth, app)
        ), patch.object(
            firebase_password, "read_new_password", return_value="new-password"
        ), patch("builtins.print"):
            firebase_password.set_password(args)

        auth.get_user_by_email.assert_called_once_with(
            "person@example.com", app=app
        )
        auth.update_user.assert_called_once_with(
            "uid-123", password="new-password", app=app
        )

    def test_set_password_can_be_cancelled(self):
        auth = MagicMock()
        app = object()
        auth.get_user.return_value = SimpleNamespace(uid="uid-123", email=None)
        args = SimpleNamespace(
            service_account=Path("key.json"),
            project=None,
            uid="uid-123",
            email=None,
            yes=False,
        )

        with patch.object(
                firebase_password, "initialize_auth", return_value=(auth, app)
        ), patch("builtins.input", return_value="n"), patch("builtins.print"):
            firebase_password.set_password(args)

        auth.update_user.assert_not_called()

    def test_reset_link_uses_uid_users_email(self):
        auth = MagicMock()
        app = object()
        user = SimpleNamespace(uid="uid-123", email="person@example.com")
        auth.get_user.return_value = user
        auth.generate_password_reset_link.return_value = "https://reset.example/link"
        args = SimpleNamespace(
            service_account=Path("key.json"),
            project=None,
            uid="uid-123",
            email=None,
        )

        with patch.object(
                firebase_password, "initialize_auth", return_value=(auth, app)
        ), patch("builtins.print"):
            firebase_password.generate_reset_link(args)

        auth.generate_password_reset_link.assert_called_once_with(
            "person@example.com", app=app
        )


if __name__ == "__main__":
    unittest.main()
