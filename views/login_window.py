import sys

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)


def login_user(email, password):
    from controller.auth_controller import login_user as authenticate

    return authenticate(email, password)


class LoginTaskSignals(QObject):
    finished = Signal(bool, object)


class LoginTask(QRunnable):
    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password
        self.signals = LoginTaskSignals()

    @Slot()
    def run(self):
        try:
            success, user_data = login_user(self.email, self.password)
        except Exception:
            success, user_data = False, None
        self.signals.finished.emit(success, user_data)


class LoginWindow(QMainWindow):
    loginSuccessful = Signal()
    signupRequested = Signal()

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self._login_in_progress = False
        self._login_task = None
        self.setWindowTitle("Login - Fwitter")
        self.setFixedSize(400, 600)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        # app logo ha olyan kedve lenne hogy betölti
        logo_layout = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap("./res/icons/icon.jpg")
        if not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaledToWidth(150, Qt.SmoothTransformation)
            )
        else:
            logo_label.setText("Fwitter")
            logo_label.setFont(QFont("Wix Madefor Text", 24, QFont.Bold))
        logo_label.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo_label)
        main_layout.addLayout(logo_layout)

        welcome_label = QLabel("Welcome Back")
        welcome_label.setFont(QFont("Wix Madefor Text", 18, QFont.Bold))
        welcome_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(welcome_label)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        # felhasznalo
        username_label = QLabel("Email:")
        username_label.setFont(QFont("Wix Madefor Text", 11))
        self.username_edit = QLineEdit()
        self.username_edit.setFont(QFont("Wix Madefor Text", 12))
        self.username_edit.setStyleSheet("padding: 8px;")
        self.username_edit.setPlaceholderText("Enter your email")
        form_layout.addWidget(username_label)
        form_layout.addWidget(self.username_edit)

        # jelszo
        password_label = QLabel("Password:")
        password_label.setFont(QFont("Wix Madefor Text", 11))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setFont(QFont("Wix Madefor Text", 12))
        self.password_edit.setStyleSheet("padding: 8px;")
        self.password_edit.setPlaceholderText("Enter your password")
        form_layout.addWidget(password_label)
        form_layout.addWidget(self.password_edit)

        # belepes
        self.login_button = QPushButton("Login")
        self.login_button.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))
        self.login_button.setStyleSheet(
            """
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border-radius: 4px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #0d65d9;
            }
        """
        )
        self.login_button.clicked.connect(self.authenticate_user)
        self.password_edit.returnPressed.connect(self.authenticate_user)
        form_layout.addWidget(self.login_button)

        # Regisztráció
        signup_layout = QHBoxLayout()
        signup_layout.setAlignment(Qt.AlignCenter)
        signup_text = QLabel("Don't have an account?")
        signup_text.setFont(QFont("Wix Madefor Text", 10))
        signup_link = QLabel("Sign up")
        signup_link.setFont(QFont("Wix Madefor Text", 10))
        signup_link.setStyleSheet("color: #0066cc; text-decoration: underline;")
        signup_link.setCursor(Qt.PointingHandCursor)
        signup_link.mousePressEvent = self.open_signup_window
        signup_layout.addWidget(signup_text)
        signup_layout.addWidget(signup_link)

        form_layout.addLayout(signup_layout)
        main_layout.addLayout(form_layout)
        main_layout.addStretch()

        self.setCentralWidget(main_widget)

    def open_signup_window(self, event):
        self.signupRequested.emit()

    @Slot()
    def authenticate_user(self):
        """Authenticate the user with the provided credentials"""
        if self._login_in_progress:
            return

        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        # Basic validation
        if not username or not password:
            QMessageBox.warning(
                self, "Login Failed", "Please enter both username and password"
            )
            return

        self._set_login_in_progress(True)
        self._login_task = LoginTask(username, password)
        self._login_task.signals.finished.connect(self._on_login_finished)
        self.thread_pool.start(self._login_task)

    def _set_login_in_progress(self, in_progress):
        self._login_in_progress = in_progress
        self.login_button.setEnabled(not in_progress)
        self.username_edit.setEnabled(not in_progress)
        self.password_edit.setEnabled(not in_progress)
        self.login_button.setText("Logging in..." if in_progress else "Login")

    @Slot(bool, object)
    def _on_login_finished(self, success, _user_data):
        self._login_task = None
        self._set_login_in_progress(False)
        if success:
            self.loginSuccessful.emit()
            self.close()
            return

        QMessageBox.warning(self, "Login failed", "Invalid username or password")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec_())
