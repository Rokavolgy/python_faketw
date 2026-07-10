from PySide6.QtCore import Qt, QEvent, QSize, QBuffer
from PySide6.QtGui import QPixmap, QMovie
from PySide6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QLabel

from widgets.avif_widget import AvifWidget


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

    def set_animation_source(self, animation_source):
        if self._cleaned_up or not isinstance(animation_source, tuple):
            return

        media_type, source = animation_source
        self.original_pixmap = None
        self.image_label.clear()
        self._reset_animation()

        if media_type == "gif_file":
            self.movie = QMovie(source)
        elif media_type == "gif_data" and isinstance(source, bytes):
            self.movie_buffer = QBuffer()
            self.movie_buffer.setData(source)
            self.movie_buffer.open(QBuffer.ReadOnly)
            self.movie = QMovie()
            self.movie.setDevice(self.movie_buffer)
        elif media_type == "avif_file":
            self.animation_widget = AvifWidget(self)
            self.animation_widget.setAlignment(Qt.AlignCenter)
            self.animation_widget.setScaledSize(self._preview_size())
            if self.animation_widget.setAvifFile(source):
                self._set_scroll_widget(self.animation_widget)
                self.animation_widget.startAnimation()
            return
        elif media_type == "avif_data" and isinstance(source, bytes):
            self.animation_widget = AvifWidget(self)
            self.animation_widget.setAlignment(Qt.AlignCenter)
            self.animation_widget.setScaledSize(self._preview_size())
            if self.animation_widget.setAvifData(source):
                self._set_scroll_widget(self.animation_widget)
                self.animation_widget.startAnimation()
            return

        if self.movie and self.movie.isValid():
            self.movie.setScaledSize(self._preview_size())
            self.movie.setCacheMode(QMovie.CacheNone)
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
        if self.animation_widget or self.movie:
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
        if not self.original_pixmap:
            return

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
        self._loader_task = None
        self.image_url = ""
        self.zoom_factor = 1.0
        self.dragging = False
        self.last_mouse_position = None
