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
    QCheckBox,
)

from controller.firestore import register_user
from profile_edit_window import ProfileEditWindow
from modal.user import ProfileData


class SignupWindow(QMainWindow):
    signupSuccessful = pyqtSignal(ProfileData)
    registrationCompleted = pyqtSignal(ProfileData)
    loginRequested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fwitter - Sign Up")
        self.setFixedSize(450, 600)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        logo_layout = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap("./assets/logo.png")
        if not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaledToWidth(150, Qt.SmoothTransformation)
            )
        else:
            logo_label.setText("Social Media App")
            logo_label.setFont(QFont("Wix Madefor Text", 24, QFont.Bold))
        logo_label.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo_label)
        main_layout.addLayout(logo_layout)

        welcome_label = QLabel("Create Your Account")
        welcome_label.setFont(QFont("Wix Madefor Text", 18, QFont.Bold))
        welcome_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(welcome_label)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)


        email_label = QLabel("Email:")
        email_label.setFont(QFont("Wix Madefor Text", 11))
        self.email_edit = QLineEdit()
        self.email_edit.setFont(QFont("Wix Madefor Text", 12))
        self.email_edit.setStyleSheet("padding: 8px;")
        self.email_edit.setPlaceholderText("Enter your email address")
        form_layout.addWidget(email_label)
        form_layout.addWidget(self.email_edit)

        password_label = QLabel("Password:")
        password_label.setFont(QFont("Wix Madefor Text", 11))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setFont(QFont("Wix Madefor Text", 12))
        self.password_edit.setStyleSheet("padding: 8px;")
        self.password_edit.setPlaceholderText("Create a password")
        form_layout.addWidget(password_label)
        form_layout.addWidget(self.password_edit)

        confirm_password_label = QLabel("Confirm Password:")
        confirm_password_label.setFont(QFont("Wix Madefor Text", 11))
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit.setFont(QFont("Wix Madefor Text", 12))
        self.confirm_password_edit.setStyleSheet("padding: 8px;")
        self.confirm_password_edit.setPlaceholderText("Confirm your password")
        form_layout.addWidget(confirm_password_label)
        form_layout.addWidget(self.confirm_password_edit)

        terms_layout = QHBoxLayout()
        self.terms_checkbox = QCheckBox(
            "Az alkalmazás használata során úgy teszek, mintha lennének \nfelhasználási feltételek és az adataimra nagyon vigyáznak. ")
        self.terms_checkbox.setFont(QFont("Wix Madefor Text", 10))
        self.terms_checkbox.setStyleSheet("padding: 8px;")
        terms_layout.addWidget(self.terms_checkbox)
        form_layout.addLayout(terms_layout)

        signup_button = QPushButton("Create Account")
        signup_button.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))
        signup_button.setStyleSheet(
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
        signup_button.clicked.connect(self.register_user)
        form_layout.addWidget(signup_button)

        # Login option
        login_layout = QHBoxLayout()
        login_layout.setAlignment(Qt.AlignCenter)
        login_text = QLabel("Already have an account?")
        login_text.setFont(QFont("Wix Madefor Text", 10))
        login_link = QLabel("Log in")
        login_link.setFont(QFont("Wix Madefor Text", 10))
        login_link.setStyleSheet("color: #0066cc; text-decoration: underline;")
        login_link.setCursor(Qt.PointingHandCursor)
        login_layout.addWidget(login_text)
        login_layout.addWidget(login_link)
        login_link.mousePressEvent = lambda event: self.loginRequested.emit()

        form_layout.addLayout(login_layout)
        main_layout.addLayout(form_layout)
        main_layout.addStretch()

        self.setCentralWidget(main_widget)

        self.profile_edit_window = None

    def register_user(self):
        """Register a new user with the provided information"""
        email = self.email_edit.text().strip()
        password = self.password_edit.text().strip()
        confirm_password = self.confirm_password_edit.text().strip()

        if not (email and password and confirm_password):
            QMessageBox.warning(
                self, "Unsuccessful registration :(", "Please fill in all fields."
            )
            return

        if password != confirm_password:
            QMessageBox.warning(
                self, "Unsuccessful registration :(", "Passwords do not match."
            )
            return

        if not self.terms_checkbox.isChecked():
            QMessageBox.warning(
                self, "Unsuccesful registration :(",
                "Jogi csapatunk szerint igazán el kellene fogadnod a regisztációs feltételeket, mert az nem lehet, hogy nem egyezel bele a nagyon egyszerű és nagyon rövid (364 oldalas) feltételekbe melyet azért hoztunk meg hogy az oldal használata igazán egyszerű legyen."
            )
            return

        try:
            success, _ = register_user(email, password)

            if success:
                profile_data = ProfileData.from_dict(_)

                QMessageBox.information(
                    self, "Succesful registration",
                    "Your account has been created. Please complete your profile in the next window."
                )

                self.open_profile_edit(profile_data)

                self.signupSuccessful.emit(profile_data)
            else:
                QMessageBox.warning(
                    self, "Unsuccessful registration :(",
                    "The email is already registered or the password is too short. Please try again."
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Registration error: {str(e)}")

    def open_profile_edit(self, profile_data):
        self.profile_edit_window = ProfileEditWindow(profile_data, True)
        self.profile_edit_window.profileCreated.connect(self.forward_profile_created)

        self.profile_edit_window.show()
        self.close()

    def forward_profile_created(self, profile_data):
        self.registrationCompleted.emit(profile_data)


# for testing (will crash)
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SignupWindow()
    window.show()
    sys.exit(app.exec_())
