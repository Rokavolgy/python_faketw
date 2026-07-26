import logging
import os

import requests
from PySide6.QtCore import QRunnable, Slot, Signal, QObject
from PySide6.QtGui import QPixmap

from controller.media_store import MediaStore

logger = logging.getLogger(__name__)


def is_gif(file_path):
    try:
        # Check if the file starts with GIF header bytes
        if file_path.endswith(".gif"):
            return True

        with open(file_path, "rb") as file:
            header = file.read(6)
            return header in [b"GIF87a", b"GIF89a"]
    except Exception as e:
        logger.debug("Could not inspect GIF file %s", file_path, exc_info=True)
        return False


def is_avif(file_path):
    try:
        if file_path.lower().endswith(".avif"):
            return True

        with open(file_path, "rb") as file:
            # Read first 32 bytes to check file signature
            header = file.read(32)

            # AVIF files are based on ISOBMFF format
            # Check for 'ftyp' box and AVIF brand
            if len(header) >= 12:
                # Skip the first 4 bytes (box size), check for 'ftyp'
                if header[4:8] == b'ftyp':
                    # Check for AVIF brand identifiers
                    brand_area = header[8:20]
                    return b'avif' in brand_area or b'avis' in brand_area

        return False
    except Exception as e:
        logger.debug("Could not inspect AVIF file %s", file_path, exc_info=True)
        return False


class ImageLoaderSignals(QObject):
    _pending_deliveries = set()

    _result_ready = Signal(object)
    _gif_ready = Signal(tuple)
    _avif_ready = Signal(tuple)
    loaded_gif_signal = Signal(tuple)
    loaded_avif_signal = Signal(tuple)  # New signal for AVIF data

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._pending_deliveries.add(self)
        self._result_ready.connect(self._deliver_result)
        self._gif_ready.connect(self._deliver_gif)
        self._avif_ready.connect(self._deliver_avif)

    def _release(self):
        self._callback = None
        self._pending_deliveries.discard(self)

    @Slot(object)
    def _deliver_result(self, payload):
        try:
            if self._callback:
                self._callback(payload)
        finally:
            self._release()

    @Slot(tuple)
    def _deliver_gif(self, payload):
        try:
            self.loaded_gif_signal.emit(payload)
        finally:
            self._release()

    @Slot(tuple)
    def _deliver_avif(self, payload):
        try:
            self.loaded_avif_signal.emit(payload)
        finally:
            self._release()


class ImageLoaderTask(QRunnable):
    """
    A QRunnable task to load an image from a URL and cache it.
    allow_gif: If True, allows GIFs to be loaded and cached as QMovie.
    allow_avif: If True, allows AVIF files to be loaded and handled properly.
    If False, GIFs/AVIF will be treated as regular images and loaded as QPixmap.
    """

    def __init__(self, image_url, callback, allow_gif=False, allow_avif=True, save_folder="cache",
                 allow_cache_file=True):
        super().__init__()
        self.image_url = image_url
        self.save_folder = save_folder
        self.allow_cache_file = allow_cache_file
        self.allow_gif = allow_gif
        self.allow_avif = allow_avif
        self.signals = ImageLoaderSignals(callback)
        self.loaded_gif_signal = self.signals.loaded_gif_signal
        self.loaded_avif_signal = self.signals.loaded_avif_signal

    @Slot()
    def run(self):
        cache_key = (
            f"{self.image_url}|gif={int(self.allow_gif)}|avif={int(self.allow_avif)}"
        )
        state, payload, event = MediaStore.acquire_media_load(cache_key)
        if state == "cached":
            self._dispatch(payload)
            return
        if state == "wait":
            payload = MediaStore.wait_for_media(cache_key, event)
            self._dispatch(payload)
            return

        try:
            payload = self._load_payload()
            if payload is None:
                MediaStore.fail_media_load(cache_key)
                self.signals._result_ready.emit(None)
                return
            MediaStore.finish_media_load(cache_key, payload)
            self._dispatch(payload)
        except Exception as e:
            MediaStore.fail_media_load(cache_key)
            logger.exception("Error loading image %s", self.image_url)
            self.signals._result_ready.emit(None)

    def _load_payload(self):
        file_name = os.path.join(self.save_folder, os.path.basename(self.image_url))
        if self.allow_cache_file and os.path.exists(file_name):
            gif_bool = is_gif(file_name)
            avif_bool = is_avif(file_name)

            if gif_bool and self.allow_gif:
                return "gif_file", file_name
            if avif_bool and self.allow_avif:
                # Route all AVIF files through the custom decoder. Qt builds
                # do not consistently include an AVIF QPixmap plugin.
                return "avif_file", file_name

            pixmap = QPixmap()
            if pixmap.load(file_name):
                return pixmap

        if self.save_folder:
            os.makedirs(self.save_folder, exist_ok=True)

        response = requests.get(self.image_url, timeout=(5, 20))
        response.raise_for_status()

        with open(file_name, "wb") as file:
            file.write(response.content)

        gif_bool = is_gif(file_name)
        avif_bool = is_avif(file_name)

        if gif_bool and self.allow_gif:
            return "gif_file", file_name
        if avif_bool and self.allow_avif:
            return "avif_file", file_name

        pixmap = QPixmap()
        if pixmap.loadFromData(response.content):
            return pixmap
        return None

    def _dispatch(self, payload):
        if isinstance(payload, tuple):
            media_type = payload[0]
            if media_type.startswith("gif_"):
                self.signals._gif_ready.emit(payload)
                return
            if media_type.startswith("avif_"):
                self.signals._avif_ready.emit(payload)
                return
        self.signals._result_ready.emit(payload)
