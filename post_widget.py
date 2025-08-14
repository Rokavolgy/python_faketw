import platform
from datetime import datetime

from PySide6.QtCore import Signal, Qt, QThreadPool
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QSizePolicy,
    QDialog,
)

if platform.system() == "Windows":
    from windows_toasts import WindowsToaster, Toast, ToastDisplayImage
else:
    WindowsToaster = None
    Toast = None
    ToastDisplayImage = None

from controller.image_loader_task import ImageLoaderTask
from controller.firestore import toggle_post_like, FirestoreListener
from controller.user_session import UserSession
from create_post_widget import CreatePostWidget
from custom_widget.like_comment_button import PostButton
from modal.constants import Constants
from modal.post import PostData


class IconCache:
    """Static cache for commonly used icons"""
    _icons = {}

    @classmethod
    def get_icon(cls, icon_path: str) -> QIcon:
        if icon_path not in cls._icons:
            cls._icons[icon_path] = QIcon(icon_path)
            print(f"Icon loaded: {icon_path}")
        return cls._icons[icon_path]

    @classmethod
    def get_pixmap(cls, icon_path: str) -> QPixmap:
        if icon_path not in cls._icons:
            cls._icons[icon_path] = QPixmap(icon_path)
        return cls._icons[icon_path]


class ClickableLabel(QLabel):
    clicked = Signal(str)

    def __init__(self, userId=None):
        super().__init__()
        self.userId = userId
        try:
            self.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    def mousePressEvent(self, event):
        if self.userId:
            self.clicked.emit(self.userId)
        else:
            self.clicked.emit("")
        super().mousePressEvent(event)


class ClickableImageLabel(QLabel):
    clicked = Signal(str)

    def __init__(self, image_url=None):
        super().__init__()
        self.image_url = image_url
        self._original_pixmap = None  # will hold full pixmap
        try:
            self.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    def mousePressEvent(self, event):
        if self.image_url:
            self.clicked.emit(self.image_url)
        else:
            self.clicked.emit("")
        super().mousePressEvent(event)


class PostsWindow(QMainWindow):
    profileSwitchRequested = Signal(str)
    commentSwitchRequested = Signal(str)
    initialFetchComplete = Signal(bool)

    def __init__(self):
        super().__init__()
        self.loading_label = None
        self.posts_layout = None
        self.posts_data = []
        if platform.system() == "Windows":
            self.toaster = WindowsToaster("Fwitter")
        else:
            self.toaster = None
        self.thread_pool = QThreadPool()
        self.listener = FirestoreListener()
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.likeUpdatedSignal.connect(self.on_post_like)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)
        self.listener.initialPostsLoadedSignal.connect(self.on_initial_fetch_complete)
        self.init_ui()


        self.listener.subscribe_to_new_posts()

    def init_ui(self):
        self.setWindowTitle("Posts Viewer")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setMaximumWidth(1000)
        scroll.setAlignment(
            Qt.AlignHCenter
        )  # miert nincs kozepen ez a vacak ??????????????????????

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.posts_layout = QVBoxLayout(container)


        for post in self.posts_data:
            post_widget = PostWidget(post)
            post_widget.profileClicked.connect(self.switch_to_profile_mode)
            post_widget.commentClicked.connect(self.switch_to_comment_mode)
            post_widget.deleteClicked.connect(self.listener.delete_post_2)
            self.posts_layout.addWidget(post_widget, stretch=1)

        self.posts_layout.addStretch()

        scroll.setWidget(container)

        main_layout.addWidget(scroll, 1)

        self.create_post_widget = CreatePostWidget(
            user_id="current_user_id", user_name="Your Username"
        )
        self.create_post_widget.postCreated.connect(self.on_post_created)

        self.create_post_widget.setMaximumHeight(200)

        main_layout.addWidget(self.create_post_widget)

        self.setCentralWidget(main_widget)

        self.initial_fetch_done = False
        self.loading_label = QLabel("Loading posts...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.posts_layout.addWidget(self.loading_label)

    def add_post_widget(self, post: PostData):
        post_widget = PostWidget(post)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        self.posts_layout.addWidget(post_widget, stretch=1)

    def switch_to_profile_mode(self, userId):
        print(f"profile show: {userId}")
        self.profileSwitchRequested.emit(userId)

    def switch_to_comment_mode(self, postId):
        print(f"comment show: {postId}")
        self.commentSwitchRequested.emit(postId)

    def on_post_created(self, new_post: PostData):
        self.add_post_widget(new_post)

        self.posts_data.insert(0, new_post)


    def on_post_notification(self, post_data: PostData):
        # keresés hogy van-e

        self.toast = Toast()
        self.toast.text_fields = ['New Post', 'Hello, World!']
        for i, post in enumerate(self.posts_data):
            if post.id == post_data.id:
                print("Poszt már létezik. Adatmódosítás.")
                self.posts_data[i] = post_data

                # Adat frissítés
                post_widget = self.posts_layout.itemAt(i).widget()
                post_widget.post_data = post_data
                post_widget.update()

                print(post_data)
                return
        self.posts_data.insert(0, post_data)

        # Only show notification if initial fetch is done
        if self.initial_fetch_done and not UserSession().user_id == post_data.userId:
            print("értesítés kapva: új poszt")
            self.toast.text_fields =["New Post", "New post from " + post_data.userName]
            if self.toaster:
                if post_data.mediaUrls:
                    image_url = Constants.STORAGE_URL + post_data.mediaUrls[0]
                    self.toast.display_image = ToastDisplayImage(image_url)
                else:
                    self.toast.display_image = None
                self.toaster.show_toast(self.toast)
        # új widget mint an onpostcreated ben
        post_widget = PostWidget(post_data)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        self.posts_layout.insertWidget(0, post_widget)

    def on_post_like(self):
        #updates elsewhere
        print("ok")
        pass

    def on_remove_from_store(self, post_id):
        for i, post in enumerate(self.posts_data):
            if post.id == post_id:
                print("Poszt törölve.")
                del self.posts_data[i]

                post_widget = self.posts_layout.itemAt(i).widget()
                self.posts_layout.removeWidget(post_widget)
                post_widget.deleteLater()
                break

    def on_initial_fetch_complete(self):
        self.initial_fetch_done = True
        self.loading_label.hide()


class PostWidget(QWidget):
    profileClicked = Signal(str)  # PostWindow
    likeClicked = Signal(str)  # FirestoreListener
    commentClicked = Signal(str)  # Nothing
    deleteClicked = Signal(str)  # FirestoreListener

    def __init__(self, post_data: PostData, hide_buttons=False):
        super().__init__()
        self.post_data = post_data
        self.thread_pool = QThreadPool()
        self.setMinimumWidth(400)
        self.setMaximumWidth(1000)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred))
        self.profile_pic = None
        self.user_info = None
        self.username = None
        self.post_content = None
        self.post_stats = None
        self.post_image = None
        self.hide_buttons = hide_buttons
        self.init_ui()

    def update_image(self, label, pixmap, height=400, width=300):
        if label is None:
            print("Warning: label not found")
        if pixmap is None or pixmap.isNull():
            return
        # Store original pixmap for full-screen / preview usage
        try:
            label._original_pixmap = pixmap
        except Exception:
            pass
        scaled_pixmap = pixmap.scaled(
            height, width, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        label.setPixmap(scaled_pixmap)

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        header_layout = QHBoxLayout()

        self.profile_pic = ClickableLabel(self.post_data.userId)
        self.profile_pic.setFixedSize(40, 40)
        self.profile_pic.setStyleSheet(
            "background-color: lightgray; border-radius: 20px;"
        )
        self.profile_pic.clicked.connect(self.on_profile_clicked)

        if self.post_data.userProfilePicUrl:
            image_url = Constants.STORAGE_URL + self.post_data.userProfilePicUrl
            task = ImageLoaderTask(
                image_url,
                lambda pixmap: self.update_image(self.profile_pic, pixmap, 40, 40),
            )
            self.thread_pool.start(task)

        header_layout.addWidget(self.profile_pic)

        user_info_layout = QVBoxLayout()

        self.username_label = QLabel(self.post_data.userName)
        self.username_label.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))

        timestamp = self.post_data.timestamp
        time_str = "Unknown date"
        if timestamp and hasattr(timestamp, "year"):
            time_str = datetime.strftime(timestamp, "%Y-%m-%d %H:%M")
        else:
            print("Érvénytelen dátum")
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet("color: gray;")

        user_info_layout.addWidget(self.username_label)
        user_info_layout.addWidget(self.time_label)
        header_layout.addLayout(user_info_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # szöveg
        self.content_label = QLabel(self.post_data.content)
        self.content_label.setFont(QFont("Wix Madefor Text", 12))
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("margin: 10px 0;")
        main_layout.addWidget(self.content_label)

        # kép
        if self.post_data.mediaUrls:
            image_url = Constants.STORAGE_URL + self.post_data.mediaUrls[0]
            self.image_label = ClickableImageLabel(image_url)
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("margin: 10px 0;")
            self.image_label.clicked.connect(self.on_image_clicked)

            # Load the image asynchronously
            task = ImageLoaderTask(
                image_url, lambda pixmap: self.update_image(self.image_label, pixmap)
            )
            self.thread_pool.start(task)

            main_layout.addWidget(self.image_label)

        # kommentelés meg kedvelés
        stats_layout = QHBoxLayout()
        stats_layout.setAlignment(Qt.AlignCenter)
        heart_filled_icon = (
            "res/icons/heart_filled.png"
            if self.post_data.likedByCurrentUser
            else "res/icons/heart.png"
        )

        # Use cached icons for better performance
        self.like_button = PostButton(
            IconCache.get_icon(heart_filled_icon),
            f" {self.post_data.likesCount}" if self.post_data.likesCount else " Like",
        )
        self.like_button.clicked.connect(
            lambda: self.on_like_clicked(self.post_data.id)
        )
        self.like_button.setFixedHeight(50)

        self.comment_button = PostButton(
            IconCache.get_icon("res/icons/comment.png"),
            (
                f" {self.post_data.commentsCount}"
                if self.post_data.commentsCount
                else " Comment"
            ),
        )
        self.comment_button.clicked.connect(
            lambda: self.on_comment_clicked(self.post_data.id)
        )
        self.comment_button.setFixedHeight(50)

        self.delete_button = PostButton(IconCache.get_icon("res/icons/delete.png"), "Delete")
        self.delete_button.clicked.connect(
            lambda: self.on_delete_clicked(self.post_data.id)
        )
        self.delete_button.setFixedHeight(50)

        if not self.hide_buttons:
            stats_layout.addWidget(self.like_button)
            stats_layout.addWidget(self.comment_button)
            stats_layout.addStretch()
            user_session = UserSession()
            if user_session.user_id == self.post_data.userId:
                stats_layout.addWidget(self.delete_button)
            main_layout.addLayout(stats_layout)

        self.separator = QLabel()
        self.separator.setFixedHeight(1)
        self.separator.setStyleSheet("background-color: lightgray;")
        main_layout.addWidget(self.separator)

        self.post_data_old = self.post_data

    def on_image_clicked(self, image_url: str):
        # Open a preview dialog with the original (unscaled) pixmap if available
        if not hasattr(self, "_image_previews"):
            self._image_previews = []  # keep references
        preview = ImagePreviewWindow(image_url)
        # If we already have the original pixmap cached on the label, set it immediately
        if hasattr(self, "image_label") and getattr(self.image_label, "_original_pixmap", None):
            preview.set_pixmap(self.image_label._original_pixmap)
        else:
            # Load (again) to ensure full-size available
            def _apply(pixmap):
                if pixmap and not pixmap.isNull():
                    preview.set_pixmap(pixmap)

            task = ImageLoaderTask(image_url, _apply)
            self.thread_pool.start(task)
        preview.show()
        self._image_previews.append(preview)

    def on_profile_clicked(self, userId):
        self.profileClicked.emit(userId)

    def on_like_clicked(self, post_id):

        self.likeClicked.emit(post_id)  # main szálon fut úgyhogy szaggat, de legalább eltakarja a nyomi animációt
        toggle_post_like(post_id)

    def on_comment_clicked(self, post_id):

        self.commentClicked.emit(post_id)
        print("Képzeletben működik a kommentelés")
        # nem csinal semmit

    def on_delete_clicked(self, post_id):
        self.deleteClicked.emit(post_id)

    def update(self):
        self.update_ui()

    def update_ui(self):
        self.content_label.setText(self.post_data.content)

        self.username_label.setText(self.post_data.userName)

        icon_path = (
            "res/icons/heart_filled.png"
            if self.post_data.likedByCurrentUser
            else "res/icons/heart.png"
        )
        # Use cached icon instead of creating new QIcon
        self.like_button.setIcon(IconCache.get_icon(icon_path))
        self.like_button.setText(
            f" {self.post_data.likesCount}" if self.post_data.likesCount else " Like"
        )

        self.comment_button.setText(
            f" {self.post_data.commentsCount}"
            if self.post_data.commentsCount
            else " Comment"
        )

        if (
                hasattr(self, "post_data_old")
                and self.post_data_old.userProfilePicUrl != self.post_data.userProfilePicUrl
        ):
            if self.post_data.userProfilePicUrl:
                image_url = Constants.STORAGE_URL + self.post_data.userProfilePicUrl
                task = ImageLoaderTask(
                    image_url,
                    lambda pixmap: self.update_image(self.profile_pic, pixmap, 40, 40),
                )
                self.thread_pool.start(task)

    def cleanup_and_delete(self):
        """
        Safely remove this widget from its parent/layout and schedule for deletion.
        """
        parent = self.parentWidget()
        if parent is not None:
            layout = parent.layout()
            if layout is not None:
                layout.removeWidget(self)
        try:
            self.delete_button.clicked.disconnect()
            self.like_button.clicked.disconnect()
            self.comment_button.clicked.disconnect()
        except Exception:
            pass
        self.setParent(None)
        self.deleteLater()


class ImagePreviewWindow(QDialog):
    def __init__(self, image_url: str):
        super().__init__()
        self.setWindowTitle("Image Preview")
        self.resize(800, 600)
        self.image_url = image_url
        self.original_pixmap = None
        layout = QVBoxLayout(self)
        self.image_label = QLabel("Loading image...")
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

    def set_pixmap(self, pixmap: QPixmap):
        # Cache original pixmap for future resizes
        if pixmap and not pixmap.isNull():
            self.original_pixmap = pixmap
            scaled = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
            self.image_label.setText("")

    def resizeEvent(self, event):
        if self.original_pixmap and not self.original_pixmap.isNull():
            scaled = self.original_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
        super().resizeEvent(event)
