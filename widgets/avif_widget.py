import hashlib
import logging
import math
import os
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QTimer, Signal, QSize, Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QLabel

from controller.media_store import MediaStore

MAX_ANIMATED_AVIF_FRAMES = 90
MAX_DECODED_AVIF_BYTES = 48 * 1024 * 1024
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AvifFrameSet:
    frames: Tuple[QPixmap, ...]
    durations: Tuple[int, ...]
    scaled_size: Optional[Tuple[int, int]]


class AvifMovie:
    """
    A movie-like class for handling animated AVIF files
    Similar to QMovie but specifically for AVIF format
    """

    def __init__(self, parent=None):
        self.parent = parent
        self.frames: List[QPixmap] = []
        self.durations: List[int] = []
        self.current_frame = 0
        self.timer = QTimer(parent)
        self.timer.timeout.connect(self._next_frame)
        self.scaled_size: Optional[QSize] = None
        self.loop_count = -1  # -1 means infinite loop
        self.current_loop = 0
        self._is_valid = False
        self._shared_frame_set: Optional[AvifFrameSet] = None

    def setFileName(self, filename: str) -> bool:
        """Load AVIF file and extract frames"""
        try:
            if not os.path.exists(filename):
                return False

            stat = os.stat(filename)
            cache_key = (
                f"avif:file:{os.path.normcase(os.path.abspath(filename))}"
                f"|{stat.st_mtime_ns}|{stat.st_size}"
            )
            cached = MediaStore.get_avif_frames(cache_key)
            if cached:
                return self._use_frame_set(cached)

            # Open the AVIF file with PIL
            with Image.open(filename) as img:
                if not hasattr(img, 'n_frames') or img.n_frames <= 1:
                    # Static image, treat as single frame
                    self._load_single_frame(img)
                else:
                    # Animated AVIF
                    self._load_animated_frames(img)

            return self._finish_decode(cache_key)

        except Exception as e:
            logger.exception("Error loading AVIF file %s", filename)
            return False

    def setData(self, data: bytes) -> bool:
        """Load AVIF from byte data"""
        try:
            cache_key = f"avif:data:{hashlib.sha256(data).hexdigest()}"
            cached = MediaStore.get_avif_frames(cache_key)
            if cached:
                return self._use_frame_set(cached)

            with Image.open(BytesIO(data)) as img:
                if not hasattr(img, 'n_frames') or img.n_frames <= 1:
                    # Static image, treat as single frame
                    self._load_single_frame(img)
                else:
                    # Animated AVIF
                    self._load_animated_frames(img)

            return self._finish_decode(cache_key)

        except Exception as e:
            logger.exception("Error loading AVIF data")
            return False

    def _load_single_frame(self, img: Image.Image):
        """Load a single frame (static image)"""
        self.frames = []
        self.durations = []

        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        pixmap = self._pil_to_qpixmap(img)
        self.frames.append(pixmap)
        self.durations.append(1000)

    def _load_animated_frames(self, img: Image.Image):
        """Load all frames from animated AVIF"""
        self.frames = []
        self.durations = []

        try:
            frame_count = getattr(img, 'n_frames', 1)
            frame_width, frame_height = img.size
            if self.scaled_size and not self.scaled_size.isEmpty():
                scale = min(
                    self.scaled_size.width() / max(1, frame_width),
                    self.scaled_size.height() / max(1, frame_height),
                    1.0,
                )
                frame_width = max(1, int(frame_width * scale))
                frame_height = max(1, int(frame_height * scale))

            bytes_per_frame = max(1, frame_width * frame_height * 4)
            memory_frame_limit = max(2, MAX_DECODED_AVIF_BYTES // bytes_per_frame)
            frame_limit = max(
                2, min(MAX_ANIMATED_AVIF_FRAMES, memory_frame_limit)
            )
            frame_step = max(1, math.ceil(frame_count / frame_limit))
            for i in range(0, frame_count, frame_step):
                img.seek(i)

                duration = img.info.get('duration', 100) * frame_step
                if duration < 10:  # Minimum 10ms to prevent too fast animation
                    duration = 10

                frame = img.copy()
                if frame.mode != 'RGBA':
                    frame = frame.convert('RGBA')

                pixmap = self._pil_to_qpixmap(frame)
                self.frames.append(pixmap)
                self.durations.append(duration)

        except Exception as e:
            logger.exception("Error processing AVIF frames")

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap"""
        if self.scaled_size and not self.scaled_size.isEmpty():
            max_size = (self.scaled_size.width(), self.scaled_size.height())
            pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)

        img_data = pil_image.tobytes('raw', 'RGBA')

        qimage = QImage(img_data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)

        return QPixmap.fromImage(qimage)

    def _finish_decode(self, cache_key):
        self._is_valid = bool(self.frames)
        if not self._is_valid:
            return False

        frame_set = AvifFrameSet(
            frames=tuple(self.frames),
            durations=tuple(self.durations),
            scaled_size=self._scaled_size_tuple(),
        )
        self._shared_frame_set = frame_set
        byte_size = sum(
            frame.width() * frame.height() * 4 for frame in frame_set.frames
        )
        MediaStore.put_avif_frames(cache_key, frame_set, byte_size)
        return True

    def _use_frame_set(self, frame_set):
        target_size = self._scaled_size_tuple()
        if target_size and target_size != frame_set.scaled_size:
            self.frames = [
                frame.scaled(
                    self.scaled_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                for frame in frame_set.frames
            ]
            self._shared_frame_set = None
        else:
            # QPixmap copies are implicitly shared, so pixels are not duplicated.
            self.frames = list(frame_set.frames)
            self._shared_frame_set = frame_set
        self.durations = list(frame_set.durations)
        self._is_valid = bool(self.frames)
        return self._is_valid

    def _scaled_size_tuple(self):
        if not self.scaled_size or self.scaled_size.isEmpty():
            return None
        return self.scaled_size.width(), self.scaled_size.height()

    def setScaledSize(self, size: QSize):
        """Set the scaled size for frames"""
        self.scaled_size = size

        if self.frames:
            original_frames = self.frames.copy()
            self.frames = []
            self._shared_frame_set = None

            for pixmap in original_frames:
                scaled_pixmap = pixmap.scaled(
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.frames.append(scaled_pixmap)

    def start(self):
        """Start the animation"""
        if not self._is_valid or not self.frames:
            return

        self.current_frame = 0
        self.current_loop = 0

        if len(self.frames) > 1:
            self.timer.start(self.durations[0])

    def stop(self):
        """Stop the animation"""
        self.timer.stop()

    def clear(self):
        """Release decoded frame memory immediately."""
        self.stop()
        try:
            self.timer.timeout.disconnect(self._next_frame)
        except Exception:
            pass
        self.frames = []
        self.durations = []
        self.current_frame = 0
        self.current_loop = 0
        self._is_valid = False
        self._shared_frame_set = None

    def setPaused(self, paused: bool):
        """Pause or resume the animation"""
        if paused:
            self.timer.stop()
        else:
            if self._is_valid and len(self.frames) > 1:
                self.timer.start(self.durations[self.current_frame])

    def _next_frame(self):
        """Move to the next frame"""
        if not self.frames:
            return

        self.current_frame = (self.current_frame + 1) % len(self.frames)

        if self.current_frame == 0:
            self.current_loop += 1
            if self.loop_count >= 0 and self.current_loop >= self.loop_count:
                self.stop()
                return

        if len(self.frames) > 1:
            self.timer.start(self.durations[self.current_frame])

    def currentPixmap(self) -> Optional[QPixmap]:
        """Get the current frame as QPixmap"""
        if not self.frames or self.current_frame >= len(self.frames):
            return None
        return self.frames[self.current_frame]

    def frameCount(self) -> int:
        """Get the total number of frames"""
        return len(self.frames)

    def isValid(self) -> bool:
        """Check if the movie is valid"""
        return self._is_valid

    def currentFrameNumber(self) -> int:
        """Get the current frame number"""
        return self.current_frame


class AvifWidget(QLabel):
    """
    A QLabel-based widget for displaying AVIF files
    Works similarly to QLabel with QMovie but for AVIF format
    """

    frameChanged = Signal(int)  # Signal emitted when frame changes
    finished = Signal()  # Signal emitted when animation finishes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.avif_movie: Optional[AvifMovie] = None
        self._scaled_size: Optional[QSize] = None
        self._disposed = False
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_display)

    def setAvifMovie(self, movie: AvifMovie):
        """Set the AVIF movie to display"""
        if self.avif_movie:
            self.avif_movie.clear()

        self.avif_movie = movie

        if movie and movie.isValid():
            self._update_timer.start(50)  # Update display every 50ms
            self._update_display()

    def setAvifFile(self, filename: str) -> bool:
        """Load and set AVIF file directly"""
        movie = AvifMovie(self)
        if self._scaled_size:
            movie.setScaledSize(self._scaled_size)
        if movie.setFileName(filename):
            self.setAvifMovie(movie)
            return True
        return False

    def setAvifData(self, data: bytes) -> bool:
        """Load and set AVIF from byte data"""
        movie = AvifMovie(self)
        if self._scaled_size:
            movie.setScaledSize(self._scaled_size)
        if movie.setData(data):
            self.setAvifMovie(movie)
            return True
        return False

    def startAnimation(self):
        """Start the AVIF animation"""
        if self.avif_movie:
            self.avif_movie.start()

    def stopAnimation(self):
        """Stop the AVIF animation"""
        if self.avif_movie:
            self.avif_movie.stop()
        self._update_timer.stop()

    def clearAnimation(self):
        """Stop playback and release decoded AVIF frames."""
        self._update_timer.stop()
        self.clear()
        if self.avif_movie:
            self.avif_movie.clear()
            self.avif_movie = None

    def dispose(self):
        """Permanently release timers, signals, and decoded frame memory."""
        if self._disposed:
            return
        self._disposed = True
        self.clearAnimation()
        try:
            self._update_timer.timeout.disconnect(self._update_display)
        except Exception:
            pass

    def setPaused(self, paused: bool):
        """Pause or resume the animation"""
        if self.avif_movie:
            self.avif_movie.setPaused(paused)

    def setScaledSize(self, size: QSize):
        """Set the scaled size for the AVIF"""
        self._scaled_size = size
        if self.avif_movie:
            self.avif_movie.setScaledSize(size)

    def _update_display(self):
        """Update the displayed frame"""
        if not self.avif_movie:
            return

        current_pixmap = self.avif_movie.currentPixmap()
        if current_pixmap:
            self.setPixmap(current_pixmap)
            self.frameChanged.emit(self.avif_movie.currentFrameNumber())

    def isAnimated(self) -> AvifMovie | None | bool:
        """Check if the current AVIF is animated"""
        return self.avif_movie and self.avif_movie.frameCount() > 1

    def frameCount(self) -> int:
        """Get the total number of frames"""
        return self.avif_movie.frameCount() if self.avif_movie else 0

    def currentFrameNumber(self) -> int:
        """Get the current frame number"""
        return self.avif_movie.currentFrameNumber() if self.avif_movie else 0
