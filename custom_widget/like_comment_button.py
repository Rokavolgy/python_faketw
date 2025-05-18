from PyQt5.QtCore import QSize, Qt, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QPushButton


class PostButton(QPushButton):
    """Custom button with animation for likes and comments"""

    def __init__(self, icon_path, text, parent=None):
        super().__init__(text, parent)
        self.setIcon(QIcon(icon_path))
        self.setIconSize(QSize(20, 20))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            """
            QPushButton {
                border: none;
                background-color: transparent;
                padding: 5px 10px;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """
        )
        self.animation = QPropertyAnimation(self, b"iconSize")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.OutBounce)

    def mousePressEvent(self, event):
        # Start animation from current size to larger size and back
        self.animation.setStartValue(QSize(20, 20))
        self.animation.setEndValue(QSize(26, 26))
        self.animation.start()

        # Schedule another animation to restore size
        QTimer.singleShot(150, self.animate_back)

        super().mousePressEvent(event)

    def animate_back(self):
        self.animation.setStartValue(QSize(26, 26))
        self.animation.setEndValue(QSize(20, 20))
        self.animation.start()
