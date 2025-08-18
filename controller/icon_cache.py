from PySide6.QtGui import QIcon, QPixmap


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
