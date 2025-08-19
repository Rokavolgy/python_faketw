import os
from io import BytesIO

import requests
from PySide6.QtCore import QRunnable, Slot, Signal, QObject
from PySide6.QtGui import QPixmap


def is_gif(file_path):
    try:
        # Check if the file starts with GIF header bytes
        if file_path.endswith(".gif"):
            return True

        with open(file_path, "rb") as file:
            header = file.read(6)
            return header in [b"GIF87a", b"GIF89a"]
    except Exception as e:
        print(f"Error reading file: {e}")
        return False


class ImageLoaderSignals(QObject):
    loaded_gif_signal = Signal(tuple)

class ImageLoaderTask(QRunnable):
    """
    A QRunnable task to load an image from a URL and cache it.
    allow_gif: If True, allows GIFs to be loaded and cached as QMovie.
    If False, GIFs will be treated as regular images and loaded as QPixmap.
    """

    def __init__(self, image_url, callback, allow_gif=False, save_folder="cache", allow_cache_file=True):
        super().__init__()
        self.image_url = image_url
        self.callback = callback
        self.save_folder = save_folder
        self.allow_cache_file = allow_cache_file
        self.allow_gif = allow_gif
        self.signals = ImageLoaderSignals()
        self.loaded_gif_signal = self.signals.loaded_gif_signal

    @Slot()
    def run(self):
        try:
            file_name = os.path.join(self.save_folder, os.path.basename(self.image_url))
            if self.allow_cache_file:
                if os.path.exists(file_name):
                    gif_bool = is_gif(file_name)
                    if gif_bool and self.allow_gif:
                        with open(file_name, "rb") as file:
                            gif_data = file.read()
                        self.loaded_gif_signal.emit(("gif_data", gif_data))
                        return
                    else:
                        pixmap = QPixmap()
                        if pixmap.load(file_name):
                            self.callback(pixmap)

            # if self.image_url in ImageLoaderTask.cache:
            #    self.callback(ImageLoaderTask.cache[self.image_url])
            #    return

            if self.save_folder:
                os.makedirs(self.save_folder, exist_ok=True)

            response = requests.get(self.image_url)
            response.raise_for_status()
            image_data = BytesIO(response.content)

            with open(file_name, "wb") as file:
                file.write(response.content)

            gif_bool = is_gif(file_name)
            if gif_bool and self.allow_gif:
                self.callback(("gif_data", response.content))
            else:
                pixmap = QPixmap()
                if pixmap.loadFromData(bytes(image_data.getbuffer())):
                    self.callback(pixmap)
        except Exception as e:
            print(f"Error loading image: {e}")
            self.callback(None)
        finally:
            self.loaded_gif_signal.disconnect()
