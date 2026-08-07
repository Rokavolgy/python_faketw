"""Small, shared QMovie configuration helpers."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QMovie

MAX_CACHED_GIF_BYTES = 6 * 1024 * 1024


def movie_source_size(movie: QMovie) -> QSize:
    source_size = movie.frameRect().size()
    if source_size.isEmpty() and movie.jumpToFrame(0):
        source_size = movie.currentPixmap().size()
    return QSize(source_size)


def fitted_movie_size(movie: QMovie, bounds: QSize) -> QSize:
    source_size = movie_source_size(movie)
    if source_size.isEmpty():
        return QSize(max(1, bounds.width()), max(1, bounds.height()))

    fitted = QSize(source_size)
    fitted.scale(bounds, Qt.KeepAspectRatio)
    return QSize(max(1, fitted.width()), max(1, fitted.height()))


def estimated_frame_cache_bytes(movie: QMovie, scaled_size: QSize):
    frame_count = movie.frameCount()
    if frame_count <= 0:
        return None
    return scaled_size.width() * scaled_size.height() * 4 * frame_count


def configure_qmovie(
        movie: QMovie,
        bounds: QSize,
        cache_budget: int = MAX_CACHED_GIF_BYTES,
) -> QSize:
    scaled_size = fitted_movie_size(movie, bounds)
    movie.set_scaled_size(scaled_size)
    decoded_bytes = estimated_frame_cache_bytes(movie, scaled_size)
    cache_all = decoded_bytes is not None and decoded_bytes <= cache_budget
    movie.setCacheMode(QMovie.CacheAll if cache_all else QMovie.CacheNone)
    return scaled_size
