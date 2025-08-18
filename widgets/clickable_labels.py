from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel


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
