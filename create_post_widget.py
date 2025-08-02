import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QFont
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
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from controller.image_uploader import ImageUploader
from controller.user_session import UserSession
from modal.post import PostData


def generate_random_uuid():
    return str(uuid.uuid4())


class CreatePostWidget(QWidget):
    postCreated = Signal(
        PostData
    )

    def __init__(self, user_id, user_name):
        super().__init__()
        self.user_id = user_id
        self.user_name = user_name
        self.selected_image_path = None
        self.image_uploader = ImageUploader()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # fejléc
        header_label = QLabel("Create New Post")
        header_label.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))
        layout.addWidget(header_label)

        self.content_editor = QTextEdit()
        self.content_editor.setPlaceholderText("What's on your mind?")
        self.content_editor.setMinimumHeight(100)
        layout.addWidget(self.content_editor)

        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumHeight(200)
        self.image_preview.setStyleSheet(
            "background-color: #f0f0f0; border: 1px dashed #ccc;"
        )
        self.image_preview.setVisible(False)
        layout.addWidget(self.image_preview)

        buttons_layout = QHBoxLayout()

        self.add_image_btn = QPushButton("Add Image")
        self.add_image_btn.setIcon(QIcon.fromTheme("insert-image"))
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
            "background-color: #1DA1F2; color: white; font-weight: bold;"
        )
        self.post_btn.clicked.connect(self.submit_post)
        buttons_layout.addWidget(self.post_btn)

        layout.addLayout(buttons_layout)

    def select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Image Files (*.png *.jpg *.jpeg)"
        )

        if file_path:
            self.selected_image_path = file_path
            self.display_image_preview(file_path)
            self.remove_image_btn.setVisible(True)

    def display_image_preview(self, image_path):
        return
        # Szétcsúszik tőle sajna :(
        # pixmap = QPixmap(image_path)
        # scaled_pixmap = pixmap.scaled(
        #    400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation
        # )
        # self.image_preview.setPixmap(scaled_pixmap)
        # self.image_preview.setVisible(True)

    def remove_image(self):
        self.selected_image_path = None
        self.image_preview.clear()
        self.image_preview.setVisible(False)
        self.remove_image_btn.setVisible(False)

    def submit_post(self):
        content = self.content_editor.toPlainText().strip()

        if not content and not self.selected_image_path:
            QMessageBox.warning(
                self, "Empty Post", "Please enter some text or add an image."
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
            print("Hiba történt az upload során:", error_msg)
            QMessageBox.critical(
                self, "Upload Failed", f"Failed to upload image: {error_msg}"
            )

        self.image_uploader.signals.success_signal.connect(on_upload_success)
        self.image_uploader.signals.failure_signal.connect(on_upload_failure)
        self.image_uploader.upload_image(
            self.selected_image_path,
        )

    def create_post(self, content, image_url=None):
        from controller.firestore import (
            create_new_post,
        )

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

                # self.postCreated.emit(post)
            else:
                QMessageBox.warning(
                    self, "Error", "Failed to create"
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"hiba: {str(e)}")

        finally:
            self.post_btn.setEnabled(True)
            self.post_btn.setText("Post")
