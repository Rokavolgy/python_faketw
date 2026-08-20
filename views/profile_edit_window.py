from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot, QThreadPool, QDate
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QScrollArea, QDateEdit,
)
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from controller.firebase_client import clear_cache
from controller.image_loader_task import ImageLoaderTask
from controller.image_uploader import ImageUploader
from controller.user_session import UserSession
from modal.constants import Constants
from modal.user import ProfileData
from widgets.clickable_labels import ClickableLabel


class ProfileEditWindow(QMainWindow):
    profileUpdated = Signal(ProfileData)
    profileCreated = Signal(ProfileData)
    user_data: ProfileData

    def __init__(self, profile_data=None, is_registering=False):
        super().__init__()
        self.thread_pool = QThreadPool()
        self.user_data = profile_data
        self.image_uploader = ImageUploader()
        self.new_profile_pic_path = None
        self.new_cover_pic_path = None
        self.is_registering = is_registering

        self.setWindowTitle("Fwitter - Edit Profile")
        self.setMinimumSize(1200, 800)

        # Load user data and initialize UI
        self.init_ui()
        self.show()

    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        form_layout = QVBoxLayout(container)
        form_layout.setSpacing(15)

        # Title
        title = QLabel("Edit your profile")
        title.setFont(QFont("Wix Madefor Text", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        form_layout.addWidget(title)

        # Profile picture section
        pic_layout = QHBoxLayout()

        profile_pic_container = QWidget()
        profile_pic_container_layout = QVBoxLayout(profile_pic_container)
        profile_pic_container_layout.setAlignment(Qt.AlignHCenter)

        self.profile_pic_label = ClickableLabel()
        self.profile_pic_label.setFixedSize(120, 120)
        self.profile_pic_label.setStyleSheet(
            "background: palette(base); border: 1px solid palette(mid);"
        )
        self.profile_pic_label.setAlignment(Qt.AlignCenter)
        self.profile_pic_label.clicked.connect(self.select_profile_picture)
        profile_pic_container_layout.addWidget(self.profile_pic_label)

        cover_pic_container = QWidget()
        cover_pic_container_layout = QVBoxLayout(cover_pic_container)
        cover_pic_container_layout.setAlignment(Qt.AlignHCenter)

        self.cover_pic_label = ClickableLabel()
        self.cover_pic_label.setFixedSize(600, 150)
        self.cover_pic_label.setStyleSheet(
            "background: palette(base); border: 1px solid palette(mid);"
        )
        self.cover_pic_label.setAlignment(Qt.AlignCenter)
        self.cover_pic_label.clicked.connect(self.select_cover_picture)
        cover_pic_container_layout.addWidget(self.cover_pic_label)

        if self.user_data.profileImageUrl:
            image_url = Constants.STORAGE_URL + self.user_data.profileImageUrl
            task = ImageLoaderTask(image_url, self.update_profile_image)
            self.thread_pool.start(task)

        if self.user_data.coverImageUrl:
            image_url = Constants.STORAGE_URL + self.user_data.coverImageUrl
            task = ImageLoaderTask(image_url, self.update_cover_image)
            self.thread_pool.start(task)

        pic_layout.addStretch()
        pic_layout.addWidget(cover_pic_container)
        pic_layout.addWidget(profile_pic_container)
        pic_layout.addStretch()

        form_layout.addLayout(pic_layout)

        # Username field
        username_layout = QVBoxLayout()
        username_label = QLabel("Username:")
        username_label.setFont(QFont("Wix Madefor Text", 11))
        self.username_edit = QLineEdit(self.user_data.username)
        self.username_edit.setFont(QFont("Wix Madefor Text", 12))
        self.username_edit.setStyleSheet("padding: 8px;")
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_edit)
        form_layout.addLayout(username_layout)

        # Display name field
        display_name_layout = QVBoxLayout()
        display_name_label = QLabel("Display Name:")
        display_name_label.setFont(QFont("Wix Madefor Text", 11))
        self.display_name_edit = QLineEdit(self.user_data.displayName or "")
        self.display_name_edit.setFont(QFont("Wix Madefor Text", 12))
        self.display_name_edit.setStyleSheet("padding: 8px;")
        display_name_layout.addWidget(display_name_label)
        display_name_layout.addWidget(self.display_name_edit)
        form_layout.addLayout(display_name_layout)

        # Bio field
        bio_layout = QVBoxLayout()
        bio_label = QLabel("Bio:")
        bio_label.setFont(QFont("Wix Madefor Text", 11))
        self.bio_edit = QTextEdit(self.user_data.bio or "")
        self.bio_edit.setFont(QFont("Wix Madefor Text", 12))
        self.bio_edit.setMinimumHeight(100)
        self.bio_edit.setStyleSheet("padding: 8px;")
        bio_layout.addWidget(bio_label)
        bio_layout.addWidget(self.bio_edit)
        form_layout.addLayout(bio_layout)

        # Location field
        location_layout = QVBoxLayout()
        location_label = QLabel("Location:")
        location_label.setFont(QFont("Wix Madefor Text", 11))
        self.location_edit = QLineEdit(self.user_data.location or "")
        self.location_edit.setFont(QFont("Wix Madefor Text", 12))
        self.location_edit.setStyleSheet("padding: 8px;")
        location_layout.addWidget(location_label)
        location_layout.addWidget(self.location_edit)
        form_layout.addLayout(location_layout)

        # Birth of date
        date_layout = QVBoxLayout()
        date_edit = QLabel("Birth Date:")
        date_edit.setFont(QFont("Wix Madefor Text", 11))
        date = QDate()
        date.setDate(self.user_data.dateOfBirth.year, self.user_data.dateOfBirth.month, self.user_data.dateOfBirth.day)
        self.date_edit = QDateEdit(date)
        self.date_edit.setFont(QFont("Wix Madefor Text", 12))
        self.date_edit.setStyleSheet("padding: 8px;")
        self.date_edit.setMaximumDate(QDate.currentDate())
        date_layout.addWidget(date_edit)
        date_layout.addWidget(self.date_edit)
        form_layout.addLayout(date_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFont(QFont("Wix Madefor Text", 12))
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.clicked.connect(self.close)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))
        self.save_btn.setMinimumWidth(150)
        self.save_btn.clicked.connect(self.save_profile)

        if self.is_registering:
            self.cancel_btn.setText("Back")
            self.save_btn.setText("Finish Registration")
        if not self.is_registering:
            button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.save_btn)

        form_layout.addLayout(button_layout)
        form_layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self.setCentralWidget(main_widget)

    @Slot(object)
    def update_profile_image(self, pixmap):
        """Update profile image in the UI"""
        self._set_centered_preview(self.profile_pic_label, pixmap)

    @Slot(object)
    def update_cover_image(self, pixmap):
        """Update profile image in the UI"""
        self._set_centered_preview(self.cover_pic_label, pixmap)

    @staticmethod
    def _set_centered_preview(label, pixmap):
        if pixmap is None or pixmap.isNull():
            label.clear()
            return

        target_size = label.size()
        scaled = pixmap.scaled(
            target_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        left = max(0, (scaled.width() - target_size.width()) // 2)
        top = max(0, (scaled.height() - target_size.height()) // 2)
        label.setPixmap(
            scaled.copy(left, top, target_size.width(), target_size.height())
        )

    @Slot()
    def select_profile_picture(self):
        """Open file dialog to select a new profile picture"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Profile Picture", "", "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            self.new_profile_pic_path = file_path
            pixmap = QPixmap(file_path)
            self.update_profile_image(pixmap)

    @Slot()
    def select_cover_picture(self):
        """Open file dialog to select a new cover picture"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cover Picture", "", "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            self.new_cover_pic_path = file_path
            pixmap = QPixmap(file_path)
            self.update_cover_image(pixmap)

    def validate_data(self):
        """Validate the input data"""
        username = self.username_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "Error", "Username is empty.")
            return False
        if not all(c.isascii() and (c.isalnum() or c == '_') for c in username):
            QMessageBox.warning(self, "Error", "The username can only contain letters, numbers, and underscores.")
            return False
        if len(self.username_edit.text().strip()) < 3:
            QMessageBox.warning(self, "Error", "Username is too short.")
            return False
        if len(self.username_edit.text().strip()) > 30:
            QMessageBox.warning(self, "Error", "Username is too long.")
            return False
        if not self.display_name_edit.text().strip():
            QMessageBox.warning(self, "Error", "Display name cannot be empty.")
            return False
        if len(self.display_name_edit.text().strip()) > 40:
            QMessageBox.warning(self, "Error", "Display name cannot exceed 40 characters.")
            return False
        if len(self.display_name_edit.text().strip()) < 3:
            QMessageBox.warning(self, "Error", "Display name must be at least 3 characters long.")
            return False
        if not self.bio_edit.toPlainText().strip():
            QMessageBox.warning(self, "Error", "Bio cannot be empty.")
            return False
        if len(self.bio_edit.toPlainText().strip()) > 500:
            QMessageBox.warning(self, "Error", "Bio cannot exceed 500 characters.")
            return False
        if not self.location_edit.text().strip():
            QMessageBox.warning(self, "Error", "Location cannot be empty.")
            return False
        if len(self.location_edit.text().strip()) > 100:
            QMessageBox.warning(self, "Error", "Location cannot exceed 100 characters.")
            return False
        return True  # these are also validated on firestore

    @Slot()
    def save_profile(self):
        """Save profile changes to backend"""
        # Validate input
        if not self.validate_data():
            return
        username = self.username_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "error", "username is not valid")
            return
        self.user_data = UserSession().profile_data
        qdate = self.date_edit.date()
        if self.user_data:
            self.user_data.username = username
            self.user_data.displayName = self.display_name_edit.text().strip()
            self.user_data.bio = self.bio_edit.toPlainText().strip()
            self.user_data.location = self.location_edit.text().strip()
            self.user_data.dateOfBirth = datetime(qdate.year(), qdate.month(), qdate.day())
        else:
            self.user_data = ProfileData(
                id=UserSession().user_id,
                website="",
                dateOfBirth=datetime(qdate.year(), qdate.month(), qdate.day()),
                createdAt= SERVER_TIMESTAMP,
                profileImageUrl="",
                coverImageUrl="",
                username=username,
                displayName=self.display_name_edit.text().strip(),
                bio=self.bio_edit.toPlainText().strip(),
                location=self.location_edit.text().strip(),
            )
        if self.new_profile_pic_path:
            self.save_profile_pic_then_continue()
            return
        else:
            if self.new_cover_pic_path:
                self.save_cover_pic_then_continue()
                return
            else:
                self.finalize_save()

    def save_profile_pic_then_continue(self):
        def continue_after_upload(image_url):
            self.user_data.profileImageUrl = image_url
            if self.new_cover_pic_path:
                self.save_cover_pic_then_continue()
            else:
                self.finalize_save()

        self._upload_profile_asset(self.new_profile_pic_path, continue_after_upload)

    def save_cover_pic_then_continue(self):
        def continue_after_upload(image_url):
            self.user_data.coverImageUrl = image_url
            self.finalize_save()

        self._upload_profile_asset(self.new_cover_pic_path, continue_after_upload)

    def _upload_profile_asset(self, path, continue_after_upload):
        def disconnect_handlers():
            self.image_uploader.signals.success_signal.disconnect(on_upload_success)
            self.image_uploader.signals.failure_signal.disconnect(on_upload_failure)

        def on_upload_success(image_url):
            disconnect_handlers()
            continue_after_upload(image_url)

        def on_upload_failure(error_msg):
            disconnect_handlers()
            QMessageBox.critical(
                self, "Upload Failed", f"Failed to upload image: {error_msg}"
            )

        self.image_uploader.signals.success_signal.connect(on_upload_success)
        self.image_uploader.signals.failure_signal.connect(on_upload_failure)
        self.image_uploader.upload_image(path, compress=True)

    def finalize_save(self):
        try:
            from controller.user_controller import (create_user_profile, update_user_profile)


            if self.is_registering:
                success = create_user_profile(UserSession().user_id, self.user_data)
                if not success:
                    QMessageBox.critical(self, "Error", "Failed to create profile.")
                    return
                clear_cache()
                UserSession().set_profile_data(self.user_data)
                self.profileCreated.emit(self.user_data)
                self.close()
            else:
                success = update_user_profile(UserSession().user_id, self.user_data)
                if not success:
                    QMessageBox.critical(self, "Error", "Failed to update profile.")
                    return
                clear_cache()
                self.profileUpdated.emit(self.user_data)
                self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update profile: {e}")
