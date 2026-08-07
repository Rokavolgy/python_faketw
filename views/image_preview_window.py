from PySide6.QtCore import Qt, QEvent, QSize, QBuffer
from PySide6.QtGui import QPixmap, QMovie
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QScrollArea, QLabel

from widgets.avif_widget import AvifWidget
from widgets.qmovie_pipeline import movie_source_size

PREVIEW_WIDTH_BUFFER = 48
PREVIEW_HEIGHT_BUFFER = 28
PREVIEW_SCREEN_WIDTH_RATIO = 0.9
PREVIEW_SCREEN_HEIGHT_RATIO = 0.85
MIN_PREVIEW_CONTENT_EDGE = 320
MAX_ZOOMED_MEDIA_EDGE = 4000


def preview_window_size(media_size: QSize, available_size: QSize) -> QSize:
    if (
            media_size.width() <= 0
            or media_size.height() <= 0
            or available_size.width() <= 0
            or available_size.height() <= 0
    ):
        return QSize(800, 600)

    max_window_width = max(1, int(available_size.width() * PREVIEW_SCREEN_WIDTH_RATIO))
    max_window_height = max(1, int(available_size.height() * PREVIEW_SCREEN_HEIGHT_RATIO))
    max_content_width = max(1, max_window_width - PREVIEW_WIDTH_BUFFER)
    max_content_height = max(1, max_window_height - PREVIEW_HEIGHT_BUFFER)

    fit_scale = min(
        max_content_width / media_size.width(),
        max_content_height / media_size.height(),
    )
    minimum_scale = MIN_PREVIEW_CONTENT_EDGE / max(
        media_size.width(), media_size.height()
    )
    scale = min(fit_scale, max(1.0, minimum_scale))

    content_width = max(1, round(media_size.width() * scale))
    content_height = max(1, round(media_size.height() * scale))
    return QSize(
        min(max_window_width, content_width + PREVIEW_WIDTH_BUFFER),
        min(max_window_height, content_height + PREVIEW_HEIGHT_BUFFER),
    )


class ImagePreviewWindow(QDialog):
    def __init__(self, image_url: str, user_name: str):
        super().__init__()
        self.setWindowTitle(user_name + "'s image")
        self.resize(800, 600)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.image_url = image_url
        self.original_pixmap = None
        self.animation_widget = None
        self.movie = None
        self.movie_buffer = None
        self.movie_source_size = None
        self._movie_paused_for_visibility = False
        self.zoom_factor = 1.0  # Start zoomed out
        self.dragging = False
        self.last_mouse_position = None
        self._cleaned_up = False
        self._loader_task = None

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

    def retain_loader_task(self, task):
        self._loader_task = task

    def release_loader_task(self):
        self._loader_task = None

    def set_pixmap(self, pixmap: QPixmap):
        if self._cleaned_up:
            return
        if pixmap and not pixmap.isNull():
            self._reset_animation()
            if self.scroll_area.widget() is not self.image_label:
                self._set_scroll_widget(self.image_label)
            size = pixmap.size()
            self._resize_to_media(size)
            # compute initial zoom to fit the viewport
            vp = self.scroll_area.viewport().size()
            if size.width() > 0 and size.height() > 0:
                fit_ratio = min(vp.width() / size.width(), vp.height() / size.height(), 1.0)
                self.zoom_factor = fit_ratio
            else:
                self.zoom_factor = 1.0
            self.original_pixmap = pixmap
            self._apply_scaled_pixmap()

    def set_animation_source(self, animation_source):
        if self._cleaned_up or not isinstance(animation_source, tuple):
            return

        media_type, source = animation_source
        self.original_pixmap = None
        self.image_label.clear()
        self._reset_animation()

        if media_type == "gif_file":
            self.movie = QMovie(source)
            self.movie.setParent(self)
        elif media_type == "gif_data" and isinstance(source, bytes):
            self.movie = QMovie(self)
            self.movie_buffer = QBuffer(self.movie)
            self.movie_buffer.setData(source)
            self.movie_buffer.open(QBuffer.ReadOnly)
            self.movie.setDevice(self.movie_buffer)
        elif media_type == "avif_file":
            self.animation_widget = AvifWidget(self)
            self.animation_widget.setAlignment(Qt.AlignCenter)
            self.animation_widget.set_scaled_size(self._preview_size())
            if self.animation_widget.setAvifFile(source):
                frame = self.animation_widget.avif_movie.current_pixmap()
                if frame:
                    self._resize_to_media(frame.size())
                    self.animation_widget.set_scaled_size(
                        self._fitted_preview_size(frame.size())
                    )
                self._set_scroll_widget(self.animation_widget)
                self.animation_widget.startAnimation()
            return
        elif media_type == "avif_data" and isinstance(source, bytes):
            self.animation_widget = AvifWidget(self)
            self.animation_widget.setAlignment(Qt.AlignCenter)
            self.animation_widget.set_scaled_size(self._preview_size())
            if self.animation_widget.setAvifData(source):
                frame = self.animation_widget.avif_movie.current_pixmap()
                if frame:
                    self._resize_to_media(frame.size())
                    self.animation_widget.set_scaled_size(
                        self._fitted_preview_size(frame.size())
                    )
                self._set_scroll_widget(self.animation_widget)
                self.animation_widget.startAnimation()
            return

        if self.movie and self.movie.isValid():
            media_size = movie_source_size(self.movie)
            self._resize_to_media(media_size)
            self.movie_source_size = QSize(media_size)
            self.zoom_factor = self._fit_zoom(self.movie_source_size)
            self.movie.setCacheMode(QMovie.CacheNone)
            self._apply_scaled_movie()
            self.image_label.setMovie(self.movie)
            self._set_scroll_widget(self.image_label)
            self.movie.start()

    def _set_scroll_widget(self, widget):
        current_widget = self.scroll_area.widget()
        if current_widget is widget:
            return
        if current_widget:
            detached_widget = self.scroll_area.takeWidget()
            if detached_widget is self.image_label:
                detached_widget.setParent(self)
        self.scroll_area.setWidget(widget)

    def _preview_size(self):
        viewport_size = self.scroll_area.viewport().size()
        width = max(1, viewport_size.width())
        height = max(1, viewport_size.height())
        return QSize(width, height)

    def _fitted_preview_size(self, media_size):
        fitted_size = QSize(media_size)
        fitted_size.scale(self._preview_size(), Qt.KeepAspectRatio)
        return fitted_size

    def _resize_to_media(self, media_size):
        screen = self.screen() or QApplication.primaryScreen()
        available_size = (
            screen.availableGeometry().size() if screen else QSize(1280, 800)
        )
        self.resize(preview_window_size(media_size, available_size))

    def _reset_animation(self):
        if self.animation_widget:
            animation_widget = self.animation_widget
            if self.scroll_area and self.scroll_area.widget() is animation_widget:
                self.scroll_area.takeWidget()
            animation_widget.dispose()
            animation_widget.clear()
            animation_widget.setParent(None)
            animation_widget.deleteLater()
            self.animation_widget = None
        if self.movie:
            movie = self.movie
            if self.image_label:
                try:
                    self.image_label.setMovie(None)
                except TypeError:
                    self.image_label.clear()
            movie.stop()
            movie.deleteLater()
            self.movie = None
        if self.movie_buffer:
            self.movie_buffer.close()
            self.movie_buffer.deleteLater()
            self.movie_buffer = None
        self.movie_source_size = None
        if self.image_label:
            self.image_label.setMinimumSize(0, 0)
        self._movie_paused_for_visibility = False

    def _fit_zoom(self, source_size):
        viewport = self.scroll_area.viewport().size()
        return min(
            viewport.width() / max(1, source_size.width()),
            viewport.height() / max(1, source_size.height()),
            1.0,
        )

    def _bounded_scaled_size(self, source_size):
        width = source_size.width() * self.zoom_factor
        height = source_size.height() * self.zoom_factor
        if width > MAX_ZOOMED_MEDIA_EDGE or height > MAX_ZOOMED_MEDIA_EDGE:
            adjustment = MAX_ZOOMED_MEDIA_EDGE / max(width, height)
            self.zoom_factor *= adjustment
            width *= adjustment
            height *= adjustment
        return QSize(max(1, round(width)), max(1, round(height)))

    def _update_media_extent(self, media_size):
        viewport = self.scroll_area.viewport()
        label_size = QSize(
            max(viewport.width(), media_size.width()),
            max(viewport.height(), media_size.height()),
        )
        self.image_label.setMinimumSize(label_size)
        self.image_label.resize(label_size)

        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        hbar.setMinimum(-100)
        hbar.setMaximum(max(0, media_size.width() - viewport.width() + 100))
        vbar.setMinimum(-100)
        vbar.setMaximum(max(0, media_size.height() - viewport.height() + 100))

    def _apply_scaled_movie(self):
        if not self.movie or not self.movie_source_size:
            return
        scaled_size = self._bounded_scaled_size(self.movie_source_size)
        self.movie.set_scaled_size(scaled_size)
        self._update_media_extent(scaled_size)

    def _apply_scaled_pixmap(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            scaled_size = self._bounded_scaled_size(self.original_pixmap.size())
            scaled = self.original_pixmap.scaled(
                scaled_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
            self._update_media_extent(scaled.size())

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            self.wheelEvent(event)
            return True
        return False

    def wheelEvent(self, event):
        if self.animation_widget or (not self.movie and not self.original_pixmap):
            event.ignore()
            return
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
        if self._movie_paused_for_visibility and self.movie:
            self.movie.set_paused(False)
        self._movie_paused_for_visibility = False
        self._update_zoom_and_scroll()

    def hideEvent(self, event):
        if self.movie and self.movie.state() == QMovie.Running:
            self.movie.set_paused(True)
            self._movie_paused_for_visibility = True
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_zoom_and_scroll()

    def _update_zoom_and_scroll(self, mouse_pos=None, old_hval=None, old_vval=None, zoom_delta=None):
        if not self.scroll_area:
            return
        if self.original_pixmap and not self.original_pixmap.isNull():
            source_size = self.original_pixmap.size()
        elif self.movie and self.movie_source_size:
            source_size = self.movie_source_size
        else:
            return

        # vp = self.scroll_area.viewport()
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()

        old_img_width = source_size.width() * self.zoom_factor
        old_img_height = source_size.height() * self.zoom_factor

        if zoom_delta:
            self.zoom_factor *= zoom_delta
            self.zoom_factor = max(0.1, min(self.zoom_factor, 10))

        if not mouse_pos and self.zoom_factor < 1.0:
            self.zoom_factor = self._fit_zoom(source_size)

        if self.movie:
            self._apply_scaled_movie()
        else:
            self._apply_scaled_pixmap()

        new_img_width = source_size.width() * self.zoom_factor
        new_img_height = source_size.height() * self.zoom_factor

        if mouse_pos and old_hval is not None and old_vval is not None:
            hbar.setValue(int((old_hval + mouse_pos.x()) * new_img_width / old_img_width - mouse_pos.x()))
            vbar.setValue(int((old_vval + mouse_pos.y()) * new_img_height / old_img_height - mouse_pos.y()))

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True

        if self.scroll_area:
            self.scroll_area.viewport().removeEventFilter(self)
        self._reset_animation()
        if self.image_label:
            self.image_label.clear()
            if self.scroll_area and self.scroll_area.widget() is self.image_label:
                self.scroll_area.takeWidget()
            self.image_label.setParent(None)
            self.image_label.deleteLater()

        self.image_label = None
        self.scroll_area = None
        self.original_pixmap = None
        self.movie_source_size = None
        self._loader_task = None
        self.image_url = ""
        self.zoom_factor = 1.0
        self.dragging = False
        self.last_mouse_position = None
