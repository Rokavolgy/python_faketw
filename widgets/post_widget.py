import logging
import weakref

from PySide6 import QtCore
from PySide6.QtCore import Signal, Qt, QThreadPool, QThread, QBuffer, QRunnable, Slot, QObject, QDateTime, \
    QLocale
from PySide6.QtGui import QFont, QMovie, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSizePolicy)

from controller.icon_cache import IconCache
from controller.image_loader_task import ImageLoaderTask
from controller.like_controller import set_post_like
from controller.profiler import track_execution_time
from controller.user_session import UserSession
from modal.constants import Constants
from modal.post import PostData
from views.image_preview_window import ImagePreviewWindow
from widgets.clickable_labels import ClickableLabel, ClickableImageLabel
from widgets.like_comment_button import PostButton
from widgets.qmovie_pipeline import configure_qmovie

logger = logging.getLogger(__name__)

MOVIE_PAUSED = 1 << 0
MEDIA_LOAD_STARTED = 1 << 1
LIKE_UPDATE_PENDING = 1 << 2
DISPOSED = 1 << 3

_BINDING_SHIFT = 4
_BINDING_MASK = ((1 << 16) - 1) << _BINDING_SHIFT

class LikeToggleSignals(QObject):
    finished = Signal(object)


class LikeToggleTask(QRunnable):
    def __init__(self, post_id, liked):
        super().__init__()
        self.post_id = post_id
        self.liked = liked
        self.signals = LikeToggleSignals()

    @Slot()
    def run(self):
        self.signals.finished.emit(set_post_like(self.post_id, self.liked))


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
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred))
        self.profile_pic = None
        self.username = None
        self._media_image_url = None
        self.hide_buttons = hide_buttons
        self._current_movie = None
        self._current_buffer = None
        self._stateflags = 00000000
        # self._movie_paused_for_visibility = False
        # self._media_load_started = False
        # self._like_update_pending = False
        # self._disposed = False
        self._like_task = None
        self._like_rollback = None
        #self._binding_generation = 0
        self._image_previews = []
        self.init_ui()
        if not self.lazy_media:
            self.start_media_load()

    # expriment only saves little memory usage
    @property
    def _movie_paused_for_visibility(self):
        return bool(self._stateflags & MOVIE_PAUSED)

    @property
    def _media_load_started(self):
        return bool(self._stateflags & MEDIA_LOAD_STARTED)

    @property
    def _like_update_pending(self):
        return bool(self._stateflags & LIKE_UPDATE_PENDING)

    @property
    def _disposed(self):
        return bool(self._stateflags & DISPOSED)

    @_movie_paused_for_visibility.setter
    def _movie_paused_for_visibility(self, value):
        if value:
            self._stateflags |= MOVIE_PAUSED
        else:
            self._stateflags &= ~MOVIE_PAUSED

    @_media_load_started.setter
    def _media_load_started(self, value):
        if value:
            self._stateflags |= MEDIA_LOAD_STARTED
        else:
            self._stateflags &= ~MEDIA_LOAD_STARTED

    @_like_update_pending.setter
    def _like_update_pending(self, value):
        if value:
            self._stateflags |= LIKE_UPDATE_PENDING
        else:
            self._stateflags &= ~LIKE_UPDATE_PENDING

    @_disposed.setter
    def _disposed(self, value):
        if value:
            self._stateflags |= DISPOSED
        else:
            self._stateflags &= ~DISPOSED

    @property
    def _binding_generation(self):
        return (self._stateflags & _BINDING_MASK) >> _BINDING_SHIFT

    @_binding_generation.setter
    def _binding_generation(self, value):
        self._stateflags = (
                                   self._stateflags & ~_BINDING_MASK
                           ) | ((value << _BINDING_SHIFT) & _BINDING_MASK)

    @track_execution_time
    def update_image(self, label, pixmap_or_movie, height=400, width=300):
        if self._disposed:
            return
        # if label is None:
        #    logger.warning("Cannot update image: label is missing")
        #    return
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
                self._replace_label_with_avif(label, pixmap_or_movie[1], width, height, from_file=True)
            elif pixmap_or_movie[0] == "avif_data" and isinstance(pixmap_or_movie[1], bytes):
                self._replace_label_with_avif(label, pixmap_or_movie[1], width, height, from_file=False)

    def _handle_gif_file(self, label, file_name, width, height):
        self._release_current_movie()
        movie = QMovie(file_name)
        movie.setParent(label)
        if not movie.isValid():
            logger.warning("Invalid GIF file: %s", file_name)
            movie.deleteLater()
            return

        configure_qmovie(movie, QtCore.QSize(width, height))
        movie.finished.connect(movie.start)

        self._current_movie = movie
        label.setMovie(movie)
        movie.start()

    def _handle_gif_data(self, label, gif_data, width, height):
        self._release_current_movie()
        movie = QMovie(label)
        buffer = QBuffer(movie)
        buffer.setData(gif_data)
        buffer.open(QBuffer.ReadOnly)

        movie.setDevice(buffer)
        if not movie.isValid():
            logger.warning("Invalid GIF buffer")
            buffer.close()
            movie.deleteLater()
            return

        configure_qmovie(movie, QtCore.QSize(width, height))
        movie.finished.connect(movie.start)

        # Store references to prevent garbage collection
        self._current_movie = movie
        self._current_buffer = buffer

        label.setMovie(movie)
        movie.start()


    def _replace_label_with_avif(self, label, avif_source, width, height, from_file):
        label.set_scaled_size(QtCore.QSize(width, height))
        loaded = (
            label.setAvifFile(avif_source)
            if from_file
            else label.setAvifData(avif_source)
        )
        if loaded:
            label.startAnimation()
        else:
            logger.warning("Failed to load AVIF data")

    def _apply_bound_image(self, generation, label, payload, height, width):
        if generation != self._binding_generation or self._disposed:
            return
        self.update_image(label, payload, height, width)

    def _start_profile_image_load(self):
        self.profile_pic.userId = self.post_data.userId
        self.profile_pic.clearAnimation()
        self.profile_pic.clear()
        if not self.post_data.userProfilePicUrl:
            return

        generation = self._binding_generation
        label = self.profile_pic
        image_url = Constants.STORAGE_URL + self.post_data.userProfilePicUrl
        task = ImageLoaderTask(
            image_url,
            lambda payload: self._apply_bound_image(
                generation, label, payload, 40, 40
            ),
            allow_avif=True,
        )

        def handle_profile_avif(payload):
            self._apply_bound_image(generation, label, payload, 40, 40)
            try:
                task.loaded_avif_signal.disconnect(handle_profile_avif)
            except (RuntimeError, TypeError):
                pass

        task.loaded_avif_signal.connect(handle_profile_avif)
        self.thread_pool.start(task)

    def _release_current_movie(self):
        if self._current_movie:
            image_label = getattr(self, "image_label", None)
            if image_label and image_label.movie() is self._current_movie:
                try:
                    image_label.setMovie(None)
                except TypeError:
                    image_label.clear()
            self._current_movie.stop()
            self._current_movie.deleteLater()
            self._current_movie = None
        if self._current_buffer:
            self._current_buffer.close()
            self._current_buffer.deleteLater()
            self._current_buffer = None
        self._movie_paused_for_visibility = False

    def _release_media_resources(self):
        self._release_current_movie()
        for label in (self.profile_pic, getattr(self, "image_label", None)):
            if label and hasattr(label, "clearAnimation"):
                label.clearAnimation()

    def hideEvent(self, event):
        movie = self._current_movie
        if movie and movie.state() == QMovie.Running:
            movie.set_paused(True)
            self._movie_paused_for_visibility = True
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._movie_paused_for_visibility and self._current_movie:
            self._current_movie.set_paused(False)
        self._movie_paused_for_visibility = False

    def _configure_media_label(self):
        self._media_load_started = False
        self._media_image_url = (
            Constants.STORAGE_URL + self.post_data.mediaUrls[0]
            if self.post_data.mediaUrls
            else None
        )
        self.image_label.image_url = self._media_image_url
        self.image_label.username = self.post_data.userName
        self.image_label.clearAnimation()
        self.image_label.clear()
        self.image_label.setText("Loading image..." if self._media_image_url else "")
        self.image_label.setVisible(bool(self._media_image_url))

    def _update_delete_button_visibility(self):
        self.delete_button.setVisible(
            not self.hide_buttons
            and UserSession().user_id == self.post_data.userId
        )

    def prepare_for_reuse(self):
        self._binding_generation += 1
        self._release_media_resources()
        self._media_load_started = False

    def bind_post(self, post_data):
        self.prepare_for_reuse()
        self.post_data = post_data
        self._disposed = False
        self.profile_pic.userId = post_data.userId
        self.username_label.setText(post_data.userName)
        self.content_label.setText(post_data.content)
        time = QDateTime(self.post_data.timestamp.year, self.post_data.timestamp.month, self.post_data.timestamp.day,
                         self.post_data.timestamp.hour, self.post_data.timestamp.minute,
                         self.post_data.timestamp.second)
        locale = QLocale.system()
        self.time_label.setText(f"{locale.toString(time, QLocale.FormatType.ShortFormat)}")
        self.apply_like_state(
            post_data.likedByCurrentUser,
            post_data.likesCount or 0,
        )
        self.comment_button.setText(
            f" {post_data.commentsCount}" if post_data.commentsCount else " Comment"
        )
        self._update_delete_button_visibility()
        self._configure_media_label()
        self._start_profile_image_load()
        if not self.lazy_media:
            self.start_media_load()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        header_layout = QHBoxLayout()

        self.profile_pic = ClickableLabel(self.post_data.userId)
        self.profile_pic.setFixedSize(40, 40)
        self.profile_pic.setStyleSheet(
            "background-color: palette(midlight); border-radius: 20px;"
        )
        self.profile_pic.clicked.connect(self.on_profile_clicked)

        self._start_profile_image_load()

        header_layout.addWidget(self.profile_pic)

        user_info_layout = QVBoxLayout()

        self.username_label = QLabel()
        self.username_label.setTextFormat(Qt.PlainText)
        self.username_label.setText(self.post_data.userName)
        self.username_label.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))

        try:
            time = QDateTime(self.post_data.timestamp.year, self.post_data.timestamp.month,
                             self.post_data.timestamp.day, self.post_data.timestamp.hour,
                             self.post_data.timestamp.minute, self.post_data.timestamp.second)
            locale = QLocale.system()
            self.time_label = QLabel(f"{locale.toString(time, QLocale.FormatType.ShortFormat)}")
            self.time_label.setForegroundRole(QPalette.PlaceholderText)
        except RuntimeError:
            self.time_label = QLabel(f"Unknown date")
            logger.debug("Unknown date or time")


        user_info_layout.addWidget(self.username_label)
        user_info_layout.addWidget(self.time_label)
        header_layout.addLayout(user_info_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # szöveg
        self.content_label = QLabel()
        self.content_label.setTextFormat(Qt.PlainText)
        # self.content_label.setText(self.post_data.content)
        self.content_label.setFont(QFont("Wix Madefor Text", 12))
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("margin: 10px 0;")
        main_layout.addWidget(self.content_label)

        # kép
        self.image_label = ClickableImageLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("margin: 10px 0;")
        self.image_label.setMinimumHeight(260)
        self.image_label.clicked.connect(self.on_image_clicked)
        main_layout.addWidget(self.image_label)
        self._configure_media_label()

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
            stats_layout.addWidget(self.delete_button)
            main_layout.addLayout(stats_layout)
        self._update_delete_button_visibility()

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(self.separator)

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
        if self._disposed or self._media_load_started or not self._media_image_url:
            return

        self._media_load_started = True
        generation = self._binding_generation
        label = self.image_label
        task = ImageLoaderTask(
            self._media_image_url,
            lambda payload: self._apply_bound_image(
                generation, label, payload, 400, 300
            ),
            allow_gif=True,
            allow_avif=True,
        )

        def one_time_gif_update(payload):
            self._apply_bound_image(generation, label, payload, 400, 300)
            try:
                task.loaded_gif_signal.disconnect(one_time_gif_update)
            except (RuntimeError, TypeError):
                pass

        def one_time_avif_update(payload):
            self._apply_bound_image(generation, label, payload, 400, 300)
            try:
                task.loaded_avif_signal.disconnect(one_time_avif_update)
            except (RuntimeError, TypeError):
                pass

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

        self._like_task = LikeToggleTask(post_id, optimistic_liked)
        self._like_rollback = (previous_liked, previous_count, post_id)
        self._like_task.signals.finished.connect(self._on_toggle_finished)
        self.thread_pool.start(self._like_task)

    @Slot(object)
    def _on_toggle_finished(self, result):
        task = self._like_task
        rollback = self._like_rollback
        self._like_task = None
        self._like_rollback = None
        self._like_update_pending = False

        if result is None and rollback:
            previous_liked, previous_count, post_id = rollback
            user_session = UserSession()
            if previous_liked:
                user_session.add_user_like(post_id)
            else:
                user_session.remove_user_like(post_id)
            if not self._disposed:
                self.apply_like_state(previous_liked, previous_count)
        elif result is not None and rollback:
            _, _, post_id = rollback
            user_session = UserSession()
            if result.liked:
                if not user_session.check_if_user_liked(post_id):
                    user_session.add_user_like(post_id)
            else:
                user_session.remove_user_like(post_id)
            if not self._disposed:
                self.apply_like_state(result.liked, result.likes_count)

        if not self._disposed:
            self.like_button.setEnabled(True)

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

    def apply_like_state(self, liked, likes_count):
        if self._disposed or self.post_data is None:
            return
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
        if self._disposed:
            return
        self._disposed = True
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

        self._binding_generation += 1
        self._release_media_resources()

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

        self.setParent(None)
        self.deleteLater()

    def can_recycle(self):
        return not self._like_update_pending and not getattr(
            self, "_image_previews", []
        )
