import logging
import uuid

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
)

from controller.user_session import UserSession
from modal.post import PostData

logger = logging.getLogger(__name__)


def generate_random_uuid():
    return str(uuid.uuid4())


class CreatePostWidget(QWidget):
    postCreated = Signal(
        PostData
    )

    def __init__(self):
        super().__init__()
        self.selected_image_path = None
        self.image_uploader = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.content_editor = QTextEdit()
        self.content_editor.setPlaceholderText("What's on your mind?")
        self.content_editor.setMinimumHeight(100)
        layout.addWidget(self.content_editor)

        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumHeight(200)
        self.image_preview.setStyleSheet(
            "background-color: palette(alternate-base); "
            "border: 1px dashed palette(mid);"
        )
        self.image_preview.setVisible(False)
        layout.addWidget(self.image_preview)

        buttons_layout = QHBoxLayout()

        self.add_image_btn = QPushButton("Add Image")
        self.add_image_btn.clicked.connect(self.select_image)
        buttons_layout.addWidget(self.add_image_btn)

        self.remove_image_btn = QPushButton("Remove Image")
        self.remove_image_btn.setIcon(QIcon.fromTheme("edit-delete"))
        self.remove_image_btn.clicked.connect(self.remove_image)
        self.remove_image_btn.setVisible(False)
        buttons_layout.addWidget(self.remove_image_btn)

        buttons_layout.addStretch()

        # Post button
        self.post_btn = QPushButton("Post")
        self.post_btn.setStyleSheet(
            "background-color: palette(highlight); "
            "color: palette(highlighted-text); font-weight: bold;"
        )
        self.post_btn.clicked.connect(self.submit_post)
        buttons_layout.addWidget(self.post_btn)

        layout.addLayout(buttons_layout)

    @Slot()
    def select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Image Files (*.png *.jpg *.jpeg *.gif)"
        )

        if file_path:
            self.selected_image_path = file_path
            self.display_image_preview(file_path)
            self.remove_image_btn.setVisible(True)

    def display_image_preview(self, image_path):
        return

        # pixmap = QPixmap(image_path)
        # scaled_pixmap = pixmap.scaled(
        #    400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation
        # )
        # self.image_preview.setPixmap(scaled_pixmap)
        # self.image_preview.setVisible(True)

    @Slot()
    def remove_image(self):
        self.selected_image_path = None
        self.image_preview.clear()
        self.image_preview.setVisible(False)
        self.remove_image_btn.setVisible(False)

    @Slot()
    def submit_post(self):
        content = self.content_editor.toPlainText().strip()

        if not content and not self.selected_image_path:
            QMessageBox.warning(
                self, "Empty Post", "Please enter some text or add an image."
            )
            return
        if len(content) > 4000:
            QMessageBox.warning(
                self, "Post Too Long", "Posts cannot exceed 4000 characters."
            )
            return

        self.post_btn.setEnabled(False)
        self.post_btn.setText("Posting...")

        if self.selected_image_path:
            self.upload_image_then_create_post(content)
        else:
            self.create_post(content)

    def upload_image_then_create_post(self, content):
        def on_upload_success(image_url):
            self.create_post(content, image_url)

        def on_upload_failure(error_msg):
            self.post_btn.setEnabled(True)
            self.post_btn.setText("Post")
            logger.error("Image upload failed: %s", error_msg)
            QMessageBox.critical(
                self, "Upload Failed", f"Failed to upload image: {error_msg}"
            )

        if self.image_uploader is None:
            from controller.image_uploader import ImageUploader

            self.image_uploader = ImageUploader()

        self.image_uploader.signals.success_signal.connect(on_upload_success)
        self.image_uploader.signals.failure_signal.connect(on_upload_failure)
        self.image_uploader.upload_image(
            self.selected_image_path,
            destination="post",
        )

    def create_post(self, content, image_url=None):
        from controller.post_controller import (
            create_new_post,
        )
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP

        try:
            user = UserSession()
            post = PostData(
                id=generate_random_uuid(),
                userId=user.user_id,
                userName=user.profile_data.displayName,
                content=content,
                userProfilePicUrl=user.profile_data.profileImageUrl,
                mediaUrls=(
                    [image_url] if image_url else []
                ),
                likedByCurrentUser=False,
                likesCount=0,
                commentsCount=0,
                timestamp=SERVER_TIMESTAMP,
            )

            success = create_new_post(post)

            if success:

                self.content_editor.clear()
                self.remove_image()

            else:
                QMessageBox.warning(
                    self, "Error", "Failed to create"
                )

        except Exception:
            logger.exception("Post creation failed")
            QMessageBox.critical(self, "Error", "Failed to create the post.")

        finally:
            self.post_btn.setEnabled(True)
            self.post_btn.setText("Post")
