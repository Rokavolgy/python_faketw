from datetime import datetime

from PySide6.QtCore import QTimer


def format_timestamp(timestamp) -> str:
    if timestamp and hasattr(timestamp, "year"):
        return datetime.strftime(timestamp, "%Y-%m-%d %H:%M")
    return "Unknown date"


def estimate_post_height(post, viewport_width: int, base_height: int) -> int:
    text_width = max(240, viewport_width - 48)
    characters_per_line = max(24, text_width // 9)
    content_lines = max(
        1,
        (len(post.content or "") + characters_per_line - 1)
        // characters_per_line,
    )
    return base_height + min(content_lines, 12) * 22 + (
        290 if post.mediaUrls else 0
    )


def schedule_media_load(callback) -> None:
    QTimer.singleShot(1, callback)
