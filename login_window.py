import sys
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
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

from controller.firestore import login_user


class LoginWindow(QMainWindow):
    loginSuccessful = pyqtSignal()
    signupRequested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login - Fwitter")
        self.setFixedSize(400, 600)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        # app logo ha olyan kedve lenne hogy betölti
        logo_layout = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap("./icons/icon.jpg")
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
        login_button = QPushButton("Login")
        login_button.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))
        login_button.setStyleSheet(
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
        login_button.clicked.connect(self.authenticate_user)
        form_layout.addWidget(login_button)

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

    def authenticate_user(self):
        """Authenticate the user with the provided credentials"""
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        # Basic validation
        if not username or not password:
            QMessageBox.warning(
                self, "Login Failed", "Please enter both username and password"
            )
            return

        try:
            success, user_data = login_user(username, password)

            if success:
                self.loginSuccessful.emit()
                self.close()
            else:
                QMessageBox.warning(
                    self, "Login Failed", "Invalid username or password"
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Login error: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec_())
