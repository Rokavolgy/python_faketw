import platform
from datetime import datetime

from PySide6.QtCore import Signal, Qt, QThreadPool, QEvent
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QSizePolicy,
    QDialog, )

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
    clicked = Signal(str, str)

    def __init__(self, image_url=None, username=None):
        super().__init__()
        self.image_url = image_url
        self.username = username
        self._original_pixmap = None  # will hold full pixmap

    def mousePressEvent(self, event):
        if self.image_url:
            self.clicked.emit(self.image_url, self.username)
        super().mousePressEvent(event)


class PostsWindow(QMainWindow):
    profileSwitchRequested = Signal(str)
    commentSwitchRequested = Signal(str)
    initialFetchComplete = Signal(bool)

    def __init__(self):
        super().__init__()
        # time log
        # print("PostsWindow init started")
        self.time = datetime.now()
        self.loading_label = None
        self.initial_load_count = 0
        self.posts_layout = None
        self.scroll = None
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
        #print("PostsWindow init done time: " + str(datetime.now() - self.time))

        self.listener.subscribe_to_new_posts()
        # print("PostsWindow subscribed to new posts" + str(datetime.now() - self.time))
        self.preload_while_fetching()
        #print("PostsWindow preload done time: " + str(datetime.now() - self.time))

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
        main_layout.addWidget(self.scroll, 1)

        self.create_post_widget = CreatePostWidget(
            user_id="current_user_id", user_name="Your Username"
        )
        self.create_post_widget.postCreated.connect(self.on_post_created)

        self.create_post_widget.setMaximumHeight(200)

        main_layout.addWidget(self.create_post_widget)

        self.setCentralWidget(main_widget)

        self.initial_fetch_done = False
        self.loading_label = QLabel("Refreshing posts...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.posts_layout.addWidget(self.loading_label)

    def preload_while_fetching(self):
        IconCache.get_icon("res/icons/heart.png")
        IconCache.get_icon("res/icons/heart_filled.png")
        IconCache.get_icon("res/icons/comment.png")
        IconCache.get_icon("res/icons/delete.png")


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
        # search

        self.toast = Toast()
        self.toast.text_fields = ['New Post', 'Hello, World!']
        if self.initial_fetch_done:
            for i, post in enumerate(self.posts_data):
                if post.id == post_data.id:
                    print("Poszt már létezik. Adatmódosítás.")
                    self.posts_data[i] = post_data

                    # Adat frissítés
                    post_widget = self.posts_layout.itemAt(i).widget()
                    post_widget.post_data = post_data
                    post_widget.refresh_ui()  # renamed from update()

                    print(post_data)
                    return
        self.posts_data.insert(0, post_data)

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
        #print("Widget create time: " + str(datetime.now() - self.time))


        post_widget = PostWidget(post_data)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        if self.initial_fetch_done:
            self.posts_layout.insertWidget(0, post_widget)
        else:
            self.posts_layout.addWidget(post_widget)

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
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.listener.initialPostsLoadedSignal.disconnect()
        #print("Initial fetch complete, removing loading label time: " + str(datetime.now() - self.time))
        self.loading_label.deleteLater()

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
        try:
            label._original_pixmap = pixmap
        except Exception:
            pass
        # Correct parameter order: width first, then height
        scaled_pixmap = pixmap.scaled(
            width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
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
            self.image_label = ClickableImageLabel(image_url, username=self.post_data.userName)
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("margin: 10px 0;")
            self.image_label.clicked.connect(self.on_image_clicked)

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

    def on_image_clicked(self, image_url: str, username: str):
        if not hasattr(self, "_image_previews"):
            self._image_previews = []  # keep references
        preview = ImagePreviewWindow(image_url, username)
        if hasattr(self, "image_label") and getattr(self.image_label, "_original_pixmap", None):
            preview.set_pixmap(self.image_label._original_pixmap)
        else:
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

    def refresh_ui(self):
        self.content_label.setText(self.post_data.content)
        self.username_label.setText(self.post_data.userName)
        icon_path = (
            "res/icons/heart_filled.png"
            if self.post_data.likedByCurrentUser
            else "res/icons/heart.png"
        )
        self.like_button.setIcon(IconCache.get_icon(icon_path))
        self.like_button.setText(
            f" {self.post_data.likesCount}" if self.post_data.likesCount else " Like"
        )
        self.comment_button.setText(
            f" {self.post_data.commentsCount}" if self.post_data.commentsCount else " Comment"
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
        self.post_data_old = self.post_data


class ImagePreviewWindow(QDialog):
    def __init__(self, image_url: str, user_name: str):
        super().__init__()
        self.setWindowTitle(user_name + "'s image")
        self.resize(800, 600)
        self.setWindowFlags(Qt.WindowType.Window)
        self.image_url = image_url
        self.original_pixmap = None
        self.zoom_factor = 1.0  # Start zoomed out
        self.dragging = False
        self.last_mouse_position = None

        layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea(self)

        # the qt moment where you have to disable the scrollbars 5 times
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.horizontalScrollBar().setEnabled(False)
        self.scroll_area.verticalScrollBar().setEnabled(False)

        self.image_label = QLabel("Loading image...")
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.image_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.scroll_area.viewport().installEventFilter(self)
        layout.addWidget(self.scroll_area)

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            # compute initial zoom to fit the viewport
            size = pixmap.size()
            vp = self.scroll_area.viewport().size()
            if size.width() > 0 and size.height() > 0:
                fit_ratio = min(vp.width() / size.width(), vp.height() / size.height(), 1.0)
                self.zoom_factor = fit_ratio
            else:
                self.zoom_factor = 1.0
            self.original_pixmap = pixmap
            self._apply_scaled_pixmap()

    def _apply_scaled_pixmap(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            maximum_pixel = 4000  # prevent high memory usage
            width = self.original_pixmap.width() * self.zoom_factor
            height = self.original_pixmap.height() * self.zoom_factor
            if width > maximum_pixel or height > maximum_pixel:
                scale_factor = maximum_pixel / max(width, height)
                self.zoom_factor *= scale_factor
            scaled = self.original_pixmap.scaled(
                self.original_pixmap.width() * self.zoom_factor,
                self.original_pixmap.height() * self.zoom_factor,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
            hbar = self.scroll_area.horizontalScrollBar()
            vbar = self.scroll_area.verticalScrollBar()
            hbar.setMinimum(-100)
            hbar.setMaximum(max(0, scaled.width() - self.scroll_area.viewport().width() + 100))
            vbar.setMinimum(-100)
            vbar.setMaximum(max(0, scaled.height() - self.scroll_area.viewport().height() + 100))
            # ensure label resizes to pixmap so scrollbars work xd


    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            self.wheelEvent(event)
            return True
        return False

    def wheelEvent(self, event):
        mouse_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        old_hval = hbar.value()
        old_vval = vbar.value()
        delta = event.angleDelta().y()
        zoom_delta = 1.1 if delta > 0 else (1 / 1.1 if delta < 0 else 1)
        self._update_zoom_and_scroll(mouse_pos, old_hval, old_vval, zoom_delta)
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.last_mouse_position = event.pos()

    def mouseMoveEvent(self, event):
        if self.dragging and self.last_mouse_position:
            delta = event.pos() - self.last_mouse_position
            hbar = self.scroll_area.horizontalScrollBar()
            vbar = self.scroll_area.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
            self.last_mouse_position = event.pos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.last_mouse_position = None

    def showEvent(self, event):
        super().showEvent(event)
        if self.original_pixmap and not self.original_pixmap.isNull():
            size = self.original_pixmap.size()
            vp = self.scroll_area.viewport().size()
            if size.width() > 0 and size.height() > 0:
                self.zoom_factor = min(vp.width() / size.width(), vp.height() / size.height(), 1.0)
            else:
                self.zoom_factor = 1.0
            self._apply_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_zoom_and_scroll()

    def _update_zoom_and_scroll(self, mouse_pos=None, old_hval=None, old_vval=None, zoom_delta=None):
        vp = self.scroll_area.viewport()
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()

        if self.original_pixmap:
            old_img_width = self.original_pixmap.width() * self.zoom_factor
            old_img_height = self.original_pixmap.height() * self.zoom_factor
        else:
            old_img_width = vp.width()
            old_img_height = vp.height()

        if zoom_delta:
            self.zoom_factor *= zoom_delta
            self.zoom_factor = max(0.1, min(self.zoom_factor, 10))

        if not mouse_pos and self.zoom_factor < 1.0:
            fit_ratio = min(vp.width() / self.original_pixmap.width(), vp.height() / self.original_pixmap.height(), 1.0)
            self.zoom_factor = fit_ratio

        self._apply_scaled_pixmap()

        new_img_width = self.original_pixmap.width() * self.zoom_factor
        new_img_height = self.original_pixmap.height() * self.zoom_factor

        if mouse_pos and old_hval is not None and old_vval is not None:
            hbar.setValue(int((old_hval + mouse_pos.x()) * new_img_width / old_img_width - mouse_pos.x()))
            vbar.setValue(int((old_vval + mouse_pos.y()) * new_img_height / old_img_height - mouse_pos.y()))

    def closeEvent(self, event):
        super().closeEvent(event)
        # clean up references
        self.image_label.setPixmap(QPixmap())
        self.original_pixmap = None
        self.zoom_factor = 1.0
        self.dragging = False
        self.last_mouse_position = None
        self.deleteLater()
