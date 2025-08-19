from datetime import datetime

from PySide6 import QtCore
from PySide6.QtCore import Signal, Qt, QThreadPool, QThread, QBuffer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSizePolicy)

from controller.firestore import toggle_post_like
from controller.icon_cache import IconCache
from controller.image_loader_task import ImageLoaderTask
from controller.user_session import UserSession
from modal.constants import Constants
from modal.post import PostData
from views.image_preview_window import ImagePreviewWindow
from widgets.clickable_labels import ClickableLabel, ClickableImageLabel
from widgets.like_comment_button import PostButton


class PostWidget(QWidget):
    profileClicked = Signal(str)  # PostWindow
    likeClicked = Signal(str)  # FirestoreListener
    commentClicked = Signal(str)  # Nothing
    deleteClicked = Signal(str)  # FirestoreListener

    def __init__(self, post_data: PostData, hide_buttons=False):
        super().__init__()
        self.post_data = post_data
        self.thread_pool = QThreadPool.globalInstance()
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
        self._current_movie = None
        self._current_buffer = None
        self.init_ui()

    def update_image(self, label, pixmap_or_movie, height=400, width=300):
        if label is None:
            print("Warning: label not found")
            return
        if isinstance(pixmap_or_movie, QPixmap):
            scaled_pixmap = pixmap_or_movie.scaled(
                width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label.setPixmap(scaled_pixmap)
        elif isinstance(pixmap_or_movie, tuple):
            if not QThread.currentThread().isMainThread():
                print("Warning: update_image called from non-main thread, gif will show up as static image")
            if (pixmap_or_movie[0] == "gif_data" and isinstance(pixmap_or_movie[1], bytes)):
                gif_data = pixmap_or_movie[1]
                from PySide6.QtGui import QMovie
                # Create QBuffer and QMovie on main thread
                buffer = QBuffer()
                buffer.setData(gif_data)
                buffer.open(QBuffer.ReadOnly)

                movie = QMovie()
                movie.setDevice(buffer)
                if not movie.isValid():
                    print("Warning: Invalid GIF buffer")
                    buffer.close()
                    return

                movie.setScaledSize(QtCore.QSize(width, height))
                movie.setCacheMode(QMovie.CacheAll)
                movie.finished.connect(movie.start)

                # Store references to prevent garbage collection
                self._current_movie = movie
                self._current_buffer = buffer  # Keep buffer alive

                label.setMovie(movie)
                movie.start()
                return


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
                image_url, lambda pixmap_or_movie: self.update_image(self.image_label, pixmap_or_movie), allow_gif=True
            )

            # connect to singal for gifs hopefully will change to it lateer
            def one_time_update(pixmap_or_movie):
                self.update_image(self.image_label, pixmap_or_movie)
                task.loaded_gif_signal.disconnect(one_time_update)

            task.loaded_gif_signal.connect(one_time_update)
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
            # doesnt work
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
        self.post_data_old = self.post_data
