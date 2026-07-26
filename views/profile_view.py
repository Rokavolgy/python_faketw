import gc
from datetime import datetime

from PySide6.QtCore import Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QFont, QPixmapCache
from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QPushButton,
)

from controller.firebase_client import fetch_user_info
from controller.firestore_listener import FirestoreListener, delete_post_2
from controller.image_loader_task import ImageLoaderTask
from controller.post_controller import fetch_posts_and_user_info
from controller.profiler import track_execution_time
from controller.user_session import UserSession
from modal.constants import Constants
from modal.post import PostData
from modal.user import ProfileData
from views.profile_edit_window import ProfileEditWindow
from widgets.post_widget import PostWidget


class ProfileView(QMainWindow):
    def __init__(self, user_id=None, profile_data=None, parent_window=None):
        super().__init__()
        self.user_id = user_id
        self.profile_data = profile_data
        self.parent_window = parent_window
        self.thread_pool = QThreadPool.globalInstance()
        self.profile_pic = None
        self.cover_image = None
        self.edit_window = None
        self.user_posts = []
        self.posts_scroll = None
        self.posts_layout = None
        self._cleaned_up = False

        self.listener = FirestoreListener()
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)

        if self.user_id and not self.profile_data:
            user_dict = fetch_user_info(self.user_id)
            if user_dict:
                self.profile_data = ProfileData.from_dict(user_dict)

        self.init_ui()

    @track_execution_time
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

    @Slot()
    def open_profile_edit(self):
        self.edit_window = ProfileEditWindow(self.profile_data)
        self.edit_window.profileUpdated.connect(self.on_profile_updated)

    @Slot(ProfileData)
    def on_profile_updated(self, updated_profile):
        self.profile_data = updated_profile

        old_widget = self.centralWidget()
        if old_widget:
            old_widget.deleteLater()

        self.init_ui()

    def create_posts_section(self):
        self.posts_scroll = QScrollArea()
        self.posts_scroll.setWidgetResizable(True)
        self.posts_scroll.verticalScrollBar().valueChanged.connect(
            self.schedule_lazy_media_loads
        )

        container = QWidget()
        self.posts_layout = QVBoxLayout(container)

        user_session = UserSession()
        self.user_posts = fetch_posts_and_user_info(
            self.user_id,
            limit=40,
            current_user_id=user_session.user_id,
            user_likes=user_session.user_likes or [],
        )
        for post in self.user_posts:
            post_widget = PostWidget(post, hide_buttons=True)
            post_widget.deleteClicked.connect(delete_post_2)
            self.posts_layout.addWidget(post_widget)

        self.posts_layout.addStretch()
        self.posts_scroll.setWidget(container)
        self.schedule_lazy_media_loads()

        return self.posts_scroll

    @Slot(PostData, bool)
    def on_post_notification(self, post_data, _should_notify=False):
        if post_data.userId != self.user_id:
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
        post_widget.deleteClicked.connect(delete_post_2)
        self.posts_layout.insertWidget(0, post_widget)
        self.schedule_lazy_media_loads()

    @Slot(str)
    def on_remove_from_store(self, post_id):
        for i, post in enumerate(self.user_posts):
            if post.id == post_id:
                del self.user_posts[i]

                for j in range(self.posts_layout.count() - 1):  # Excluding stretch item
                    widget = self.posts_layout.itemAt(j).widget()
                    if isinstance(widget, PostWidget) and widget.post_data.id == post_id:
                        self.posts_layout.removeWidget(widget)
                        widget.cleanup_and_delete()
                        break
                break

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    @Slot()
    def schedule_lazy_media_loads(self):
        QTimer.singleShot(0, self.load_visible_media)

    @Slot()
    def load_visible_media(self):
        if not self.posts_scroll or not self.posts_layout:
            return

        scrollbar = self.posts_scroll.verticalScrollBar()
        viewport_top = scrollbar.value()
        viewport_bottom = viewport_top + self.posts_scroll.viewport().height()
        preload_margin = 700

        for i in range(self.posts_layout.count()):
            item = self.posts_layout.itemAt(i)
            widget = item.widget() if item else None
            if not isinstance(widget, PostWidget):
                continue

            geometry = widget.geometry()
            if (
                    geometry.bottom() >= viewport_top - preload_margin
                    and geometry.top() <= viewport_bottom + preload_margin
            ):
                widget.start_media_load()

    def cleanup(self):
        if self._cleaned_up:
            return

        self._cleaned_up = True
        if hasattr(self, 'listener'):
            self.listener.stop_listening()
            try:
                self.listener.newPostsSignal.disconnect(self.on_post_notification)
                self.listener.removeFromStoreSignal.disconnect(self.on_remove_from_store)
            except Exception:
                pass

        if self.posts_layout:
            for i in reversed(range(self.posts_layout.count())):
                widget = self.posts_layout.itemAt(i).widget()
                if isinstance(widget, PostWidget):
                    widget.cleanup_and_delete()

        if self.cover_image:
            self.cover_image.clear()
        if self.profile_pic:
            self.profile_pic.clear()

        central_widget = self.takeCentralWidget()
        if central_widget:
            central_widget.setParent(None)
            central_widget.deleteLater()

        self.user_posts = []
        self.cover_image = None
        self.profile_pic = None
        self.posts_scroll = None
        self.posts_layout = None
        QPixmapCache.clear()
        QTimer.singleShot(0, gc.collect)

    def update_image(self, label, pixmap, height=400, width=300, aspect_ratio=True):
        if self._cleaned_up or label is None or pixmap is None:
            return

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

    @Slot()
    def go_back(self):
        if self.parent_window and hasattr(self.parent_window, "stacked_widget"):
            self.cleanup()
            self.parent_window.stacked_widget.setCurrentIndex(0)
            self.parent_window.stacked_widget.removeWidget(self)
            self.setParent(None)
            self.deleteLater()

        else:

            assert "the previous widget doesnt exist."
            self.close()
