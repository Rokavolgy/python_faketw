from datetime import datetime

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QPushButton,
)

from controller.firestore import fetch_user_info, fetch_posts_and_user_info, FirestoreListener
from controller.image_loader_task import ImageLoaderTask
from controller.user_session import UserSession
from modal.constants import Constants
from modal.user import ProfileData
from post_widget import PostWidget
from profile_edit_window import ProfileEditWindow


class ProfileView(QMainWindow):
    def __init__(self, user_id=None, profile_data=None, parent_window=None):
        super().__init__()
        self.user_id = user_id
        self.profile_data = profile_data
        self.parent_window = parent_window
        self.thread_pool = QThreadPool()
        self.profile_pic = None
        self.cover_image = None
        self.edit_window = None
        self.user_posts = []

        self.listener = FirestoreListener()
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)

        if self.user_id and not self.profile_data:
            user_dict = fetch_user_info(self.user_id)
            if user_dict:
                self.profile_data = ProfileData.from_dict(user_dict)

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("User Profile")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        # profile header
        header = self.create_profile_header()
        main_layout.addWidget(header)

        # post label
        posts_label = QLabel("Posts")
        posts_label.setFont(QFont("Wix Madefor Text", 14, QFont.Bold))
        main_layout.addWidget(posts_label)

        if self.user_id:
            posts_widget = self.create_posts_section()
            main_layout.addWidget(posts_widget)
        else:
            no_posts = QLabel("No posts available")
            no_posts.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(no_posts)

        # vissza
        back_button = QPushButton("Back to Feed")
        back_button.clicked.connect(self.go_back)
        main_layout.addWidget(back_button)

        self.setCentralWidget(main_widget)

    def create_profile_header(self):
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)

        self.cover_image = QLabel()
        self.cover_image.setFixedHeight(150)
        self.cover_image.setStyleSheet("background-color: #3498db;")

        if self.profile_data.coverImageUrl:
            image_url = Constants.STORAGE_URL + self.profile_data.coverImageUrl
            task = ImageLoaderTask(
                image_url,
                lambda pixmap: self.update_image(
                    self.cover_image, pixmap, 150, self.cover_image.width(), False
                ),
            )
            self.thread_pool.start(task)

        header_layout.addWidget(self.cover_image)

        # prof info
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)

        # img
        self.profile_pic = QLabel()
        self.profile_pic.setFixedSize(120, 120)
        self.profile_pic.setStyleSheet(
            "background-color: lightgray; border-radius: 10px;"
        )

        if self.profile_data.profileImageUrl:
            image_url = Constants.STORAGE_URL + self.profile_data.profileImageUrl
            task = ImageLoaderTask(
                image_url,
                lambda pixmap: self.update_image(self.profile_pic, pixmap, 120, 120),
            )
            self.thread_pool.start(task)

        info_layout.addWidget(self.profile_pic)

        # user section
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        # display name
        display_name = QLabel(
            self.profile_data.displayName if self.profile_data else "Unknown User"
        )
        display_name.setFont(QFont("Wix Madefor Text", 16, QFont.Bold))
        details_layout.addWidget(display_name)

        # username
        username = QLabel(
            f"@{self.profile_data.username}"
            if self.profile_data and self.profile_data.username
            else ""
        )
        username.setStyleSheet("color: gray;")
        details_layout.addWidget(username)

        # bio
        if self.profile_data and self.profile_data.bio:
            bio = QLabel(self.profile_data.bio)
            bio.setWordWrap(True)
            details_layout.addWidget(bio)

        # location, website, join date
        meta_widget = QWidget()
        meta_layout = QHBoxLayout(meta_widget)
        meta_layout.setContentsMargins(0, 5, 0, 5)

        if self.profile_data:
            if self.profile_data.location:
                location = QLabel(f"📍 {self.profile_data.location}")
                meta_layout.addWidget(location)

            if self.profile_data.website:
                website = QLabel(f"🔗 {self.profile_data.website}")
                meta_layout.addWidget(website)

            if self.profile_data.createdAt:
                joined_date = datetime.strftime(self.profile_data.createdAt, "%B %Y")
                joined = QLabel(f"🗓️ Joined {joined_date}")
                meta_layout.addWidget(joined)

        meta_layout.addStretch()
        details_layout.addWidget(meta_widget)
        user_session = UserSession()
        if user_session.is_authenticated and user_session.user_id == self.user_id:
            edit_button = QPushButton("Edit Profile")
            edit_button.setCursor(Qt.PointingHandCursor)
            edit_button.setStyleSheet(
                """
                 QPushButton {
                     background-color: #f0f0f0;
                     border: 1px solid #d0d0d0;
                     padding: 5px 10px;
                     border-radius: 15px;
                 }
                 QPushButton:hover {
                     background-color: #e0e0e0;
                 }
             """
            )
            edit_button.clicked.connect(self.open_profile_edit)
            details_layout.addWidget(edit_button)
        info_layout.addWidget(details_widget, 1)
        header_layout.addWidget(info_widget)

        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: lightgray;")
        header_layout.addWidget(separator)

        return header_widget

    def open_profile_edit(self):
        self.edit_window = ProfileEditWindow(self.profile_data)
        self.edit_window.profileUpdated.connect(self.on_profile_updated)

    def on_profile_updated(self, updated_profile):
        self.profile_data = updated_profile

        old_widget = self.centralWidget()
        if old_widget:
            old_widget.deleteLater()

        self.init_ui()

    def create_posts_section(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.posts_layout = QVBoxLayout(container)

        self.user_posts = fetch_posts_and_user_info(self.user_id)
        for post in self.user_posts:
            post_widget = PostWidget(post, hide_buttons=True)
            post_widget.deleteClicked.connect(self.listener.delete_post_2)
            self.posts_layout.addWidget(post_widget)

        self.posts_layout.addStretch()
        scroll.setWidget(container)

        return scroll

    def on_post_notification(self, post_data):
        if post_data.userId != self.user_id:
            print('fail')
            return

        for i, post in enumerate(self.user_posts):
            if post.id == post_data.id:
                self.user_posts[i] = post_data

                for j in range(self.posts_layout.count() - 1):
                    widget = self.posts_layout.itemAt(j).widget()
                    if isinstance(widget, PostWidget) and widget.post_data.id == post_data.id:
                        widget.post_data = post_data
                        widget.update()
                        return

        self.user_posts.insert(0, post_data)
        post_widget = PostWidget(post_data)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        self.posts_layout.insertWidget(0, post_widget)

    def on_remove_from_store(self, post_id):
        for i, post in enumerate(self.user_posts):
            if post.id == post_id:
                del self.user_posts[i]

                for j in range(self.posts_layout.count() - 1):  # Excluding stretch item
                    widget = self.posts_layout.itemAt(j).widget()
                    if isinstance(widget, PostWidget) and widget.post_data.id == post_id:
                        self.posts_layout.removeWidget(widget)
                        widget.deleteLater()
                        break
                break

    def closeEvent(self, event):
        if hasattr(self, 'listener'):
            if hasattr(self.listener, '_post_watch') and self.listener._post_watch:
                self.listener._post_watch.unsubscribe()
            if hasattr(self.listener, '_likes_watch') and self.listener._likes_watch:
                self.listener._likes_watch.unsubscribe()
        super().closeEvent(event)

    def update_image(self, label, pixmap, height=400, width=300, aspect_ratio=True):
        if aspect_ratio:
            actual_width = label.width()
            scaled_pixmap = pixmap.scaled(
                actual_width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        else:
            scaled_pixmap = pixmap.scaled(
                width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )

        label.setPixmap(scaled_pixmap)
        print("ok")

    def go_back(self):
        if self.parent_window and hasattr(self.parent_window, "stacked_widget"):
            self.parent_window.stacked_widget.setCurrentIndex(0)
            self.parent_window.stacked_widget.removeWidget(self)
            self.listener.newPostsSignal.disconnect(self.on_post_notification)
            self.listener.removeFromStoreSignal.disconnect(self.on_remove_from_store)
            for i in reversed(range(self.posts_layout.count())):
                widget = self.posts_layout.itemAt(i).widget()
                if widget is not None and isinstance(widget, PostWidget):
                    widget.cleanup_and_delete()
                    self.posts_layout.removeWidget(widget)
            self.user_posts = []

        else:

            assert "the previous widget doesnt exist."
            self.close()
