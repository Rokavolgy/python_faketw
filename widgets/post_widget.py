import logging
import weakref
from datetime import datetime

from PySide6 import QtCore
from PySide6.QtCore import Signal, Qt, QThreadPool, QThread, QBuffer, QRunnable, Slot, QObject
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSizePolicy)

from controller.icon_cache import IconCache
from controller.image_loader_task import ImageLoaderTask
from controller.like_controller import toggle_post_like
from controller.profiler import track_execution_time
from controller.user_session import UserSession
from modal.constants import Constants
from modal.post import PostData
from views.image_preview_window import ImagePreviewWindow
from widgets.avif_widget import AvifWidget
from widgets.clickable_labels import ClickableLabel, ClickableImageLabel
from widgets.like_comment_button import PostButton

logger = logging.getLogger(__name__)


class LikeToggleSignals(QObject):
    finished = Signal(bool)


class LikeToggleTask(QRunnable):
    def __init__(self, post_id, user_id):
        super().__init__()
        self.post_id = post_id
        self.user_id = user_id
        self.signals = LikeToggleSignals()

    @Slot()
    def run(self):
        self.signals.finished.emit(toggle_post_like(self.post_id, self.user_id))


class PostWidget(QWidget):
    profileClicked = Signal(str)  # PostWindow
    likeClicked = Signal(str)  # FirestoreListener
    commentClicked = Signal(str)  # Nothing
    deleteClicked = Signal(str)  # FirestoreListener

    def __init__(self, post_data: PostData, hide_buttons=False, lazy_media=True):
        super().__init__()
        self.post_data = post_data
        self.lazy_media = lazy_media
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
        self._current_avif_widget = None  # Store AVIF widget reference
        self._current_avif_widgets = []
        self._media_image_url = None
        self._media_load_started = False
        self._like_update_pending = False
        self._like_task = None
        self._like_rollback = None
        self.init_ui()
        if not self.lazy_media:
            self.start_media_load()

    @track_execution_time
    def update_image(self, label, pixmap_or_movie, height=400, width=300):
        if label is None:
            logger.warning("Cannot update image: label is missing")
            return
        if isinstance(pixmap_or_movie, QPixmap):
            scaled_pixmap = pixmap_or_movie.scaled(
                width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label.setPixmap(scaled_pixmap)
        elif isinstance(pixmap_or_movie, tuple):
            if not QThread.currentThread().isMainThread():
                logger.warning("Image animation update arrived off the UI thread")

            if pixmap_or_movie[0] == "gif_file":
                self._handle_gif_file(label, pixmap_or_movie[1], width, height)
            elif pixmap_or_movie[0] == "gif_data" and isinstance(pixmap_or_movie[1], bytes):
                self._handle_gif_data(label, pixmap_or_movie[1], width, height)
            elif pixmap_or_movie[0] == "avif_file":
                self._handle_avif_file(label, pixmap_or_movie[1], width, height)
            elif pixmap_or_movie[0] == "avif_data" and isinstance(pixmap_or_movie[1], bytes):
                self._handle_avif_data(label, pixmap_or_movie[1], width, height)

    def _handle_gif_file(self, label, file_name, width, height):
        from PySide6.QtGui import QMovie

        movie = QMovie(file_name)
        if not movie.isValid():
            logger.warning("Invalid GIF file: %s", file_name)
            return

        movie.setScaledSize(QtCore.QSize(width, height))
        movie.setCacheMode(QMovie.CacheNone)
        movie.finished.connect(movie.start)

        self._current_movie = movie
        label.setMovie(movie)
        movie.start()

    def _handle_gif_data(self, label, gif_data, width, height):
        from PySide6.QtGui import QMovie
        buffer = QBuffer()
        buffer.setData(gif_data)
        buffer.open(QBuffer.ReadOnly)

        movie = QMovie()
        movie.setDevice(buffer)
        if not movie.isValid():
            logger.warning("Invalid GIF buffer")
            buffer.close()
            return

        movie.setScaledSize(QtCore.QSize(width, height))
        movie.setCacheMode(QMovie.CacheNone)
        movie.finished.connect(movie.start)

        # Store references to prevent garbage collection
        self._current_movie = movie
        self._current_buffer = buffer

        label.setMovie(movie)
        movie.start()

    def _handle_avif_file(self, label, file_name, width, height):
        """Handle animated AVIF from a cached file without extra Python bytes."""
        self._replace_label_with_avif(label, file_name, width, height, from_file=True)

    def _handle_avif_data(self, label, avif_data, width, height):
        """Handle AVIF animation data"""
        self._replace_label_with_avif(label, avif_data, width, height, from_file=False)

    def _replace_label_with_avif(self, label, avif_source, width, height, from_file):
        # Create AVIF widget if label doesn't support AVIF natively
        if hasattr(label, 'setAvifData'):
            label.setScaledSize(QtCore.QSize(width, height))
            if from_file and hasattr(label, "setAvifFile"):
                label.setAvifFile(avif_source)
            else:
                label.setAvifData(avif_source)
            label.startAnimation()
        else:
            # Replace the label with an AVIF widget in the layout
            try:
                # Get the parent layout
                parent_layout = label.parent().layout()
                if parent_layout:
                    # Create new AVIF widget
                    avif_widget = AvifWidget(label.parent())
                    avif_widget.setAlignment(label.alignment())
                    avif_widget.setStyleSheet(label.styleSheet())

                    if label == getattr(self, "image_label", None):
                        def open_preview(event):
                            self.on_image_clicked(self._media_image_url, self.post_data.userName)
                            event.accept()

                        avif_widget.mousePressEvent = open_preview
                    elif label == self.profile_pic:
                        def open_profile(event):
                            self.on_profile_clicked(self.post_data.userId)
                            event.accept()

                        avif_widget.mousePressEvent = open_profile

                    avif_widget.setScaledSize(QtCore.QSize(width, height))
                    loaded = (
                        avif_widget.setAvifFile(avif_source)
                        if from_file
                        else avif_widget.setAvifData(avif_source)
                    )
                    if loaded:
                        avif_widget.startAnimation()

                        index = parent_layout.indexOf(label)
                        if index >= 0:
                            parent_layout.removeWidget(label)
                            parent_layout.insertWidget(index, avif_widget)
                            label.deleteLater()

                            if label == self.image_label:
                                self.image_label = avif_widget
                            elif label == self.profile_pic:
                                self.profile_pic = avif_widget

                            self._current_avif_widget = avif_widget
                            self._current_avif_widgets.append(avif_widget)
                        else:
                            logger.warning("Could not find media label in layout")
                    else:
                        logger.warning("Failed to load AVIF data")
                        avif_widget.deleteLater()
                else:
                    logger.warning("Could not find parent layout for AVIF replacement")
            except Exception as e:
                logger.exception("Error replacing label with AVIF widget")

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
                allow_avif=True  # Enable AVIF support for profile pictures too
            )

            # Handle AVIF profile pictures
            def handle_profile_avif(avif_data):
                self.update_image(self.profile_pic, avif_data, 40, 40)
                task.loaded_avif_signal.disconnect(handle_profile_avif)

            task.loaded_avif_signal.connect(handle_profile_avif)
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
            logger.debug("Post has an invalid timestamp")
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
            self._media_image_url = image_url
            self.image_label = ClickableImageLabel(image_url, username=self.post_data.userName)
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("margin: 10px 0;")
            self.image_label.setMinimumHeight(260)
            self.image_label.setText("Loading image...")
            self.image_label.clicked.connect(self.on_image_clicked)

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
        self.like_button.clicked.connect(self.on_like_clicked)
        self.like_button.setFixedHeight(50)

        self.comment_button = PostButton(
            IconCache.get_icon("res/icons/comment.png"),
            (
                f" {self.post_data.commentsCount}"
                if self.post_data.commentsCount
                else " Comment"
            ),
        )
        self.comment_button.clicked.connect(self.on_comment_clicked)
        self.comment_button.setFixedHeight(50)

        self.delete_button = PostButton(IconCache.get_icon("res/icons/delete.png"), "Delete")
        self.delete_button.clicked.connect(self.on_delete_clicked)
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

    @Slot(str, str)
    def on_image_clicked(self, image_url: str, username: str):
        if not hasattr(self, "_image_previews"):
            self._image_previews = []  # keep references
        preview = ImagePreviewWindow(image_url, username)
        preview_ref = weakref.ref(preview)
        owner_ref = weakref.ref(self)

        def _release_preview(*_args):
            owner = owner_ref()
            closed_preview = preview_ref()
            if owner is None or closed_preview is None:
                return
            try:
                owner._image_previews.remove(closed_preview)
            except (AttributeError, ValueError):
                pass

        preview.finished.connect(_release_preview)
        preview.destroyed.connect(_release_preview)

        def _apply(pixmap):
            current_preview = preview_ref()
            if current_preview:
                try:
                    if pixmap and not pixmap.isNull():
                        current_preview.set_pixmap(pixmap)
                finally:
                    current_preview.release_loader_task()

        task = ImageLoaderTask(image_url, _apply, allow_gif=True, allow_avif=True)

        def _apply_gif(gif_source):
            current_preview = preview_ref()
            if current_preview:
                try:
                    current_preview.set_animation_source(gif_source)
                finally:
                    current_preview.release_loader_task()

        def _apply_avif(avif_source):
            current_preview = preview_ref()
            if current_preview:
                try:
                    current_preview.set_animation_source(avif_source)
                finally:
                    current_preview.release_loader_task()

        task.loaded_gif_signal.connect(_apply_gif)
        task.loaded_avif_signal.connect(_apply_avif)
        preview.retain_loader_task(task)
        self.thread_pool.start(task)
        preview.show()
        self._image_previews.append(preview)

    def start_media_load(self):
        if self._media_load_started or not self._media_image_url:
            return

        self._media_load_started = True
        task = ImageLoaderTask(
            self._media_image_url,
            lambda pixmap_or_movie: self.update_image(self.image_label, pixmap_or_movie),
            allow_gif=True,
            allow_avif=True,
        )

        def one_time_gif_update(pixmap_or_movie):
            self.update_image(self.image_label, pixmap_or_movie)
            task.loaded_gif_signal.disconnect(one_time_gif_update)

        def one_time_avif_update(avif_data):
            self.update_image(self.image_label, avif_data)
            task.loaded_avif_signal.disconnect(one_time_avif_update)

        task.loaded_gif_signal.connect(one_time_gif_update)
        task.loaded_avif_signal.connect(one_time_avif_update)
        self.thread_pool.start(task)

    @Slot(str)
    def on_profile_clicked(self, userId):
        self.profileClicked.emit(userId)

    @Slot()
    def on_like_clicked(self):
        if self._like_update_pending:
            return

        post_id = self.post_data.id
        user_session = UserSession()
        if not user_session.is_authenticated:
            logger.warning("Unauthenticated like click ignored")
            return

        self.likeClicked.emit(post_id)

        previous_liked = self.post_data.likedByCurrentUser
        previous_count = self.post_data.likesCount or 0
        optimistic_liked = not previous_liked
        optimistic_count = max(0, previous_count + (1 if optimistic_liked else -1))

        self._like_update_pending = True
        self.like_button.setEnabled(False)
        self.apply_like_state(optimistic_liked, optimistic_count)

        if optimistic_liked:
            user_session.add_user_like(post_id)
        else:
            user_session.remove_user_like(post_id)

        self._like_task = LikeToggleTask(post_id, user_session.user_id)
        self._like_rollback = (previous_liked, previous_count, post_id)
        self._like_task.signals.finished.connect(self._on_toggle_finished)
        self.thread_pool.start(self._like_task)

    @Slot(bool)
    def _on_toggle_finished(self, success):
        task = self._like_task
        rollback = self._like_rollback
        self._like_task = None
        self._like_rollback = None
        self._like_update_pending = False
        self.like_button.setEnabled(True)

        if not success and rollback:
            previous_liked, previous_count, post_id = rollback
            self.apply_like_state(previous_liked, previous_count)
            user_session = UserSession()
            if previous_liked:
                user_session.add_user_like(post_id)
            else:
                user_session.remove_user_like(post_id)

        if task:
            try:
                task.signals.finished.disconnect(self._on_toggle_finished)
            except (RuntimeError, TypeError):
                pass

    @Slot()
    def on_comment_clicked(self):
        self.commentClicked.emit(self.post_data.id)

    @Slot()
    def on_delete_clicked(self):
        self.deleteClicked.emit(self.post_data.id)

    def refresh_ui(self):
        logger.debug("Refreshing post UI for %s", self.post_data.id)
        self.content_label.setText(self.post_data.content)
        self.username_label.setText(self.post_data.userName)
        self.apply_like_state(
            self.post_data.likedByCurrentUser,
            self.post_data.likesCount or 0,
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
        return

    def apply_like_state(self, liked, likes_count):
        self.post_data.likedByCurrentUser = liked
        self.post_data.likesCount = likes_count
        icon_path = (
            "res/icons/heart_filled.png"
            if self.post_data.likedByCurrentUser
            else "res/icons/heart.png"
        )
        self.like_button.setIcon(IconCache.get_icon(icon_path))
        self.like_button.setText(
            f" {self.post_data.likesCount}" if self.post_data.likesCount else " Like"
        )

    def cleanup_and_delete(self):
        """
        Safely remove this widget from its parent/layout and schedule for deletion.
        """
        logger.debug("Cleaning up post widget %s", self.post_data.id if self.post_data else None)
        self.setUpdatesEnabled(False)
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
            logger.debug("Post widget signals were already disconnected")
            pass

        # Explicitly release image resources
        if self._current_movie:
            self._current_movie.stop()
            self._current_movie.deleteLater()
            self._current_movie = None

        if self._current_buffer:
            self._current_buffer.close()
            self._current_buffer = None

        if self._current_avif_widget:
            self._current_avif_widget = None

        for avif_widget in self._current_avif_widgets:
            avif_widget.dispose()
            avif_widget.setParent(None)
            avif_widget.deleteLater()
        self._current_avif_widgets = []

        if hasattr(self, "_image_previews"):
            for preview in list(self._image_previews):
                preview.close()
            self._image_previews = []

        for label_name in ("profile_pic", "image_label", "content_label", "username_label", "time_label"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            if hasattr(label, "dispose"):
                label.dispose()
            label.clear()

        self.post_data = None
        self.post_data_old = None

        self.setParent(None)
        self.deleteLater()
