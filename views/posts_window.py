import logging
import platform
from datetime import datetime

from PySide6.QtCore import Signal, QThreadPool, Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QScrollArea, QSizePolicy, QLabel

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
from widgets.post_widget import PostWidget

logger = logging.getLogger(__name__)


def preload_while_fetching():
    IconCache.get_icon("res/icons/heart.png")
    IconCache.get_icon("res/icons/heart_filled.png")
    IconCache.get_icon("res/icons/comment.png")
    IconCache.get_icon("res/icons/delete.png")


class PostsWindow(QMainWindow):
    profileSwitchRequested = Signal(str)
    commentSwitchRequested = Signal(str)
    initialFetchComplete = Signal(bool)

    def __init__(self):
        super().__init__()
        # time log
        self.time = datetime.now()
        self.loading_label = None
        self.initial_load_count = 0
        self.posts_layout = None
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
        self.thread_pool = QThreadPool.globalInstance()
        self.listener = FirestoreListener(post_limit=40)
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.likeUpdatedSignal.connect(self.on_post_like)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)
        self.listener.initialPostsLoadedSignal.connect(self.on_initial_fetch_complete)
        self.init_ui()

        self.preload_user_likes()
        self.listener.subscribe_to_new_posts()
        preload_while_fetching()

    def init_ui(self):
        self.setWindowTitle("Posts Viewer")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setMaximumWidth(1000)
        self.scroll.setAlignment(
            Qt.AlignHCenter
        )  # ysd

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.posts_layout = QVBoxLayout(container)

        self.posts_layout.addStretch()

        self.scroll.setWidget(container)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(
            self.schedule_lazy_media_loads
        )
        main_layout.addWidget(self.scroll, 1)

        self.create_post_widget = CreatePostWidget(
            user_id="current_user_id", user_name="Your Username"
        )
        self.create_post_widget.postCreated.connect(self.on_post_created)

        self.create_post_widget.setMaximumHeight(200)

        main_layout.addWidget(self.create_post_widget)

        self.setCentralWidget(main_widget)

        self.loading_label = QLabel("Refreshing posts...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.posts_layout.addWidget(self.loading_label)

    def preload_user_likes(self):
        user_session = UserSession()
        if user_session.is_authenticated and user_session.user_likes is None:
            user_session.set_user_likes(fetch_user_likes(user_session.user_id))
        if user_session.is_authenticated:
            self.listener.set_user_likes(user_session.user_likes or [])

    def add_post_widget(self, post: PostData):
        post_widget = self.create_post_widget_for_data(post)
        self.posts_layout.addWidget(post_widget, stretch=1)
        self.schedule_lazy_media_loads()

    def insert_post_widget_sorted(self, post: PostData):
        post_widget = self.create_post_widget_for_data(post)
        insert_index = self.get_sorted_insert_index(post)
        self.posts_layout.insertWidget(insert_index, post_widget)
        self.schedule_lazy_media_loads()

    def get_sorted_insert_index(self, post: PostData):
        if not self.posts_layout:
            return 0

        for i in range(self.posts_layout.count()):
            item = self.posts_layout.itemAt(i)
            widget = item.widget() if item else None
            if not isinstance(widget, PostWidget):
                continue
            widget_post = getattr(widget, "post_data", None)
            if not widget_post or not widget_post.timestamp:
                continue
            if post.timestamp and post.timestamp > widget_post.timestamp:
                return i
        return max(0, self.posts_layout.count() - 1)

    def insert_post_data_sorted(self, post: PostData):
        for i, existing_post in enumerate(self.posts_data):
            if existing_post.id == post.id:
                self.posts_data[i] = post
                return
            if post.timestamp and existing_post.timestamp and post.timestamp > existing_post.timestamp:
                self.posts_data.insert(i, post)
                return
        self.posts_data.append(post)

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

    def find_post_widget(self, post_id):
        if not self.posts_layout:
            return None

        for i in range(self.posts_layout.count()):
            item = self.posts_layout.itemAt(i)
            widget = item.widget() if item else None
            if not isinstance(widget, PostWidget):
                continue
            post_data = getattr(widget, "post_data", None)
            if post_data and post_data.id == post_id:
                return widget
        return None

    def switch_to_profile_mode(self, userId):
        logger.debug("Opening profile view for %s", userId)
        self.profileSwitchRequested.emit(userId)

    def switch_to_comment_mode(self, postId):
        logger.debug("Opening comment view for post %s", postId)
        self.commentSwitchRequested.emit(postId)

    def on_post_created(self, new_post: PostData):
        if self.find_post_widget(new_post.id):
            return
        self.insert_post_widget_sorted(new_post)
        self.insert_post_data_sorted(new_post)

    def on_post_notification(self, post_data: PostData, should_notify=False):
        # search
        post_data.likedByCurrentUser = UserSession().check_if_user_liked(post_data.id)

        if self.initial_fetch_done:
            for i, post in enumerate(self.posts_data):
                if post.id == post_data.id:
                    logger.debug("Updating existing post %s", post_data.id)
                    self.posts_data[i] = post_data

                    # Adat frissítés
                    post_widget = self.find_post_widget(post_data.id)
                    if post_widget:
                        post_widget.post_data = post_data
                        post_widget.refresh_ui()  # renamed from update()

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
        # új widget mint an onpostcreated ben

        if self.initial_fetch_done:
            self.insert_post_widget_sorted(post_data)
        else:
            self.add_post_widget(post_data)
        self.schedule_lazy_media_loads()

    def on_post_like(self):
        # updates elsewhere
        pass

    def on_remove_from_store(self, post_id):
        post_widget = self.find_post_widget(post_id)
        if post_widget:
            post_widget.cleanup_and_delete()
            self.posts_layout.removeWidget(post_widget)
            logger.debug("Removed post %s from the feed", post_id)

        self.posts_data = [
            post for post in self.posts_data if post.id != post_id
        ]

    def on_initial_fetch_complete(self):
        self.initial_fetch_done = True
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.listener.initialPostsLoadedSignal.disconnect()
        self.loading_label.deleteLater()
        self.schedule_lazy_media_loads()

    def schedule_lazy_media_loads(self):
        QTimer.singleShot(0, self.load_visible_media)

    def load_visible_media(self):
        if not self.scroll or not self.posts_layout:
            return

        scrollbar = self.scroll.verticalScrollBar()
        viewport_top = scrollbar.value()
        viewport_bottom = viewport_top + self.scroll.viewport().height()
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
            if self.find_post_widget(post.id):
                continue
            post.likedByCurrentUser = UserSession().check_if_user_liked(post.id)
            self.insert_post_data_sorted(post)
            self.insert_post_widget_sorted(post)

        self.loading_more_posts = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_lazy_media_loads()
