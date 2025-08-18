from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QLabel


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
