import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from views.login_window import LoginWindow


class LoginWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            QTest.qWait(10)
        return False

    def test_enter_in_password_field_submits_login(self):
        window = LoginWindow()
        window.username_edit.setText("person@example.com")
        window.password_edit.setText("password123")
        window.password_edit.setFocus()

        with patch(
                "views.login_window.login_user", return_value=(False, None)
        ) as login_user, patch.object(QMessageBox, "warning"):
            QTest.keyClick(window.password_edit, Qt.Key_Return)
            self.assertTrue(self.wait_until(lambda: not window._login_in_progress))

        login_user.assert_called_once_with("person@example.com", "password123")
        window.close()

    def test_repeated_submit_is_ignored_while_login_is_running(self):
        window = LoginWindow()
        window.username_edit.setText("person@example.com")
        window.password_edit.setText("password123")
        started = threading.Event()
        release = threading.Event()

        def slow_login(email, password):
            started.set()
            release.wait(2)
            return False, None

        with patch("views.login_window.login_user", side_effect=slow_login) as login_user, \
                patch.object(QMessageBox, "warning"):
            window.authenticate_user()
            self.assertTrue(started.wait(1))
            window.authenticate_user()

            self.assertFalse(window.login_button.isEnabled())
            self.assertEqual(window.login_button.text(), "Logging in...")
            login_user.assert_called_once_with("person@example.com", "password123")

            release.set()
            self.assertTrue(self.wait_until(lambda: not window._login_in_progress))

        self.assertTrue(window.login_button.isEnabled())
        self.assertEqual(window.login_button.text(), "Login")
        window.close()

    def test_import_does_not_load_authentication_backend(self):
        environment = os.environ.copy()
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import views.login_window; "
                "print('controller.auth_controller' in sys.modules)",
            ],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
