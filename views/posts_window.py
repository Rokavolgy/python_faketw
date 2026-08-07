import logging
import platform

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSizePolicy, QLabel, QPushButton,
)

from controller.firestore_listener import FirestoreListener, delete_post_2
from controller.like_controller import fetch_user_likes
from controller.post_controller import fetch_posts_page

if platform.system() == "Windows":
    from windows_toasts import WindowsToaster, Toast, ToastDisplayImage
else:
    WindowsToaster = None
    Toast = None
    ToastDisplayImage = None

from controller.icon_cache import IconCache
from controller.user_session import UserSession
from modal.constants import Constants
from modal.post import PostData
from widgets.create_post_widget import CreatePostWidget
from widgets.post_display import estimate_post_height, schedule_media_load
from widgets.post_widget import PostWidget
from widgets.virtualized_list import VirtualizedWidgetList

logger = logging.getLogger(__name__)


def preload_while_fetching():
    IconCache.get_icon("res/icons/heart.png")
    IconCache.get_icon("res/icons/heart_filled.png")
    IconCache.get_icon("res/icons/comment.png")
    IconCache.get_icon("res/icons/delete.png")


class PostsWindow(QMainWindow):
    profileSwitchRequested = Signal(str)
    commentSwitchRequested = Signal(str)
    messagesRequested = Signal()

    def __init__(self):
        super().__init__()
        self.loading_label = None
        self.post_list = None
        self.scroll = None
        self.initial_fetch_done = False
        self.loading_more_posts = False
        self.reached_end_of_feed = False
        self.page_size = 20
        self.posts_data = []
        if platform.system() == "Windows":
            self.toaster = WindowsToaster("Fwitter")
        else:
            self.toaster = None
        self.listener = FirestoreListener(post_limit=20)
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)
        self.listener.initialPostsLoadedSignal.connect(self.on_initial_fetch_complete)
        self.init_ui()

        self.preload_user_likes()
        self.listener.subscribe_to_new_posts()
        preload_while_fetching()

    def init_ui(self):
        self.setWindowTitle("Posts Viewer")
        self.setMinimumSize(540, 720)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.post_list = VirtualizedWidgetList(
            widget_factory=self.create_post_widget_for_data,
            key_for_item=lambda post: post.id,
            estimate_height=self.estimate_post_height,
            widget_binder=lambda widget, post: widget.bind_post(post),
            materialized=self.on_post_materialized,
            dematerialized=self.on_post_dematerialized,
            can_recycle=lambda widget: widget.can_recycle(),
            overscan_rows=5,
        )
        self.scroll = self.post_list
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(
            self.schedule_lazy_media_loads
        )

        self.loading_label = QLabel("Refreshing posts...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.loading_label)
        main_layout.addWidget(self.scroll, 1)

        self.create_post_widget = CreatePostWidget()
        self.create_post_widget.postCreated.connect(self.on_post_created)

        self.create_post_widget.setMaximumHeight(200)

        main_layout.addWidget(self.create_post_widget)

        self.messages_button = QPushButton("Messages")
        self.messages_button.clicked.connect(self.messagesRequested.emit)
        main_layout.addWidget(self.messages_button)

        self.setCentralWidget(main_widget)

    def on_post_materialized(self, widget):
        widget.start_media_load()
        if widget.post_data:
            self.listener.subscribe_to_post_document(widget.post_data.id)

    def on_post_dematerialized(self, widget):
        if widget.post_data:
            self.listener.unsubscribe_from_post_document(widget.post_data.id)

    def preload_user_likes(self):
        user_session = UserSession()
        if user_session.is_authenticated and user_session.user_likes is None:
            user_session.set_user_likes(fetch_user_likes(user_session.user_id))
        if user_session.is_authenticated:
            self.listener.set_user_likes(user_session.user_likes or [])

    def insert_post_data_sorted(self, post: PostData):
        for i, existing_post in enumerate(self.posts_data):
            if existing_post.id == post.id:
                self.posts_data[i] = post
                self.post_list.update_item(post)
                return i, False
            if post.timestamp and existing_post.timestamp and post.timestamp > existing_post.timestamp:
                self.posts_data.insert(i, post)
                self.post_list.insert_item(i, post)
                return i, True
        self.posts_data.append(post)
        row = len(self.posts_data) - 1
        self.post_list.insert_item(row, post)
        return row, True

    def oldest_loaded_timestamp(self):
        timestamps = [
            post.timestamp for post in self.posts_data if getattr(post, "timestamp", None)
        ]
        if not timestamps:
            return None
        return min(timestamps)

    def create_post_widget_for_data(self, post: PostData):
        post_widget = PostWidget(post)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(delete_post_2)
        return post_widget

    @staticmethod
    def estimate_post_height(post: PostData, viewport_width: int):
        return estimate_post_height(post, viewport_width, base_height=155)

    @Slot(str)
    def switch_to_profile_mode(self, userId):
        logger.debug("Opening profile view for %s", userId)
        self.profileSwitchRequested.emit(userId)

    @Slot(str)
    def switch_to_comment_mode(self, postId):
        logger.debug("Opening comment view for post %s", postId)
        self.commentSwitchRequested.emit(postId)

    @Slot(PostData)
    def on_post_created(self, new_post: PostData):
        if any(post.id == new_post.id for post in self.posts_data):
            return
        self.insert_post_data_sorted(new_post)

    @Slot(PostData, bool)
    def on_post_notification(self, post_data: PostData, should_notify=False):
        post_data.likedByCurrentUser = UserSession().check_if_user_liked(post_data.id)

        for i, post in enumerate(self.posts_data):
            if post.id == post_data.id:
                logger.debug("Updating existing post %s", post_data.id)
                self.posts_data[i] = post_data
                self.post_list.update_item(post_data)
                return
        self.insert_post_data_sorted(post_data)

        if should_notify and not UserSession().user_id == post_data.userId:
            logger.info("New post notification for %s", post_data.id)
            if self.toaster:
                self.toast = Toast()
                self.toast.text_fields = ["New Post", "New post from " + post_data.userName]
                if post_data.mediaUrls:
                    image_url = Constants.STORAGE_URL + post_data.mediaUrls[0]
                    self.toast.display_image = ToastDisplayImage(image_url)
                else:
                    self.toast.display_image = None
                self.toaster.show_toast(self.toast)
        self.schedule_lazy_media_loads()

    @Slot(str)
    def on_remove_from_store(self, post_id):
        if self.post_list and self.post_list.remove_key(post_id):
            logger.debug("Removed post %s from the feed", post_id)

        self.posts_data = [
            post for post in self.posts_data if post.id != post_id
        ]

    @Slot()
    def on_initial_fetch_complete(self):
        self.initial_fetch_done = True
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.listener.initialPostsLoadedSignal.disconnect()
        if self.loading_label:
            self.loading_label.deleteLater()
            self.loading_label = None
        self.schedule_lazy_media_loads()

    @Slot()
    def schedule_lazy_media_loads(self):
        schedule_media_load(self.load_visible_media)

    @Slot()
    def load_visible_media(self):
        if not self.post_list:
            return

        self.post_list.schedule_sync()
        for widget in self.post_list.active_widgets():
            widget.start_media_load()

        scrollbar = self.scroll.verticalScrollBar()
        if (
                self.initial_fetch_done
                and not self.loading_more_posts
                and not self.reached_end_of_feed
                and scrollbar.maximum() - scrollbar.value() < 500
        ):
            self.load_more_posts()

    def load_more_posts(self):
        before_timestamp = self.oldest_loaded_timestamp()
        if not before_timestamp:
            return

        self.loading_more_posts = True
        older_posts = fetch_posts_page(
            before_timestamp=before_timestamp,
            limit=self.page_size,
            user_likes=UserSession().user_likes or [],
        )

        if len(older_posts) < self.page_size:
            self.reached_end_of_feed = True

        for post in older_posts:
            if any(existing.id == post.id for existing in self.posts_data):
                continue
            post.likedByCurrentUser = UserSession().check_if_user_liked(post.id)
            self.insert_post_data_sorted(post)

        self.loading_more_posts = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_lazy_media_loads()

    def closeEvent(self, event):
        self.listener.stop_listening()
        if self.post_list:
            self.post_list.clear_items()
        super().closeEvent(event)
