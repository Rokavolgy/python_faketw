"""
Animation utilities for the social app
Provides easy-to-use functions for handling animated content (GIF, AVIF)
"""

import logging

from PySide6.QtCore import QBuffer
from PySide6.QtCore import QSize, QIODevice
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QLabel

logger = logging.getLogger(__name__)

from avif_widget import AvifWidget, AvifMovie


def create_animated_label(parent=None) -> QLabel:
    """
    Create a QLabel that can handle both GIF and AVIF animations
    Returns a standard QLabel that can be used with set_animation()
    """
    return QLabel(parent)


def set_animation(label: QLabel, file_path: str = None, data: bytes = None,
                  animation_type: str = None, scaled_size: QSize = None) -> bool:
    """
    Set animation on a QLabel for both GIF and AVIF files

    Args:
        label: The QLabel to set animation on
        file_path: Path to the animation file
        data: Raw bytes of the animation file
        animation_type: 'gif', 'avif', or None for auto-detection
        scaled_size: Optional size to scale the animation to

    Returns:
        bool: True if animation was set successfully, False otherwise
    """

    # Auto-detect animation type if not specified
    if animation_type is None and file_path:
        if file_path.lower().endswith('.gif'):
            animation_type = 'gif'
        elif file_path.lower().endswith('.avif'):
            animation_type = 'avif'
        elif data:
            # Try to detect from data
            if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
                animation_type = 'gif'
            elif b'avif' in data[:100] or b'avis' in data[:100]:
                animation_type = 'avif'

    if animation_type == 'gif':
        return _set_gif_animation(label, file_path, data, scaled_size)
    elif animation_type == 'avif':
        return _set_avif_animation(label, file_path, data, scaled_size)
    else:
        logger.warning("Unknown animation type for %s", file_path or "data")
        return False


def _set_gif_animation(label: QLabel, file_path: str = None, data: bytes = None,
                       scaled_size: QSize = None) -> bool:
    """Set GIF animation on a QLabel using QMovie"""
    try:
        if data:
            buffer = QBuffer()
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)

            movie = QMovie()
            movie.setDevice(buffer)

            if not movie.isValid():
                buffer.close()
                return False

        elif file_path:
            movie = QMovie(file_path)
            if not movie.isValid():
                return False
        else:
            return False

        if scaled_size:
            movie.setScaledSize(scaled_size)

        # Set up looping
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        movie.finished.connect(movie.start)

        label.setMovie(movie)
        movie.start()

        return True

    except Exception as e:
        logger.exception("Error setting GIF animation")
        return False


def _set_avif_animation(label: QLabel, file_path: str = None, data: bytes = None,
                        scaled_size: QSize = None) -> bool:
    """Set AVIF animation on a QLabel by replacing it with AvifWidget"""
    try:
        # Create AVIF movie
        movie = AvifMovie()

        # Load the AVIF data
        if file_path:
            if not movie.setFileName(file_path):
                return False
        elif data:
            if not movie.setData(data):
                return False
        else:
            return False

        # Set scaled size if provided
        if scaled_size:
            movie.setScaledSize(scaled_size)

        # If the label is a regular QLabel, we need to replace it with AvifWidget
        # or set the AVIF frames manually
        if hasattr(label, 'setAvifMovie'):
            # Label is already an AvifWidget
            label.setAvifMovie(movie)
            label.startAnimation()
        else:
            # Convert regular QLabel to show AVIF frames
            # For now, show the first frame as a static image
            first_frame = movie.currentPixmap()
            if first_frame:
                label.setPixmap(first_frame)
                # Store the movie reference to prevent garbage collection
                label._avif_movie = movie
                movie.start()

        return True

    except Exception as e:
        logger.exception("Error setting AVIF animation")
        return False


def create_avif_widget(parent=None) -> AvifWidget:
    """
    Create a dedicated AVIF widget for better AVIF animation support

    Returns:
        AvifWidget: A widget specifically designed for AVIF animations
    """
    return AvifWidget(parent)


def is_animated_file(file_path: str) -> bool:
    """
    Check if a file is an animated image format (GIF or AVIF)

    Args:
        file_path: Path to the file to check

    Returns:
        bool: True if file appears to be animated, False otherwise
    """
    try:
        if file_path.lower().endswith('.gif'):
            return True
        elif file_path.lower().endswith('.avif'):
            # Check if AVIF is animated by trying to load it
            from PIL import Image
            with Image.open(file_path) as img:
                return hasattr(img, 'n_frames') and img.n_frames > 1
    except (TypeError, RuntimeError) as e:
        logger.warning("unable to determine if file is animated")
        pass
    finally:
        return False
