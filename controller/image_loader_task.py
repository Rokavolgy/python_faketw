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


def is_avif(file_path):
    try:
        with open(file_path, "rb") as file:
            # Check ftyp section
            file.seek(8)
            ftyp = file.read(4).decode("ascii", errors="ignore")
            if ftyp not in ["avis", "avif"]:
                return False  # Not an AVIF file

            # Search for stsz section
            file.seek(0)
            data = file.read()
            stsz_index = data.find(b"stsz")
            if stsz_index == -1:
                return False  # No stsz section found

            num_frames = int.from_bytes(data[stsz_index + 12:stsz_index + 16], "big")
            return num_frames > 1  # True if more than 1 frame
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
                    avif_bool = is_avif(file_name)
                    if gif_bool and self.allow_gif:
                        with open(file_name, "rb") as file:
                            gif_data = file.read()
                        self.loaded_gif_signal.emit(("gif_data", gif_data))
                        return
                    elif avif_bool and self.allow_gif:
                        self.handle_animated_avif(file_name)
                        return
                    else:
                        pixmap = QPixmap()
                        if pixmap.load(file_name):
                            self.callback(pixmap)
                            return

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
            avif_bool = is_avif(file_name)
            if gif_bool and self.allow_gif:
                self.callback(("gif_data", response.content))
            elif avif_bool and self.allow_gif:
                self.handle_animated_avif(file_name)
                return
            else:
                pixmap = QPixmap()
                if pixmap.loadFromData(bytes(image_data.getbuffer())):
                    self.callback(pixmap)
        except Exception as e:
            print(f"Error loading image: {e}")
            self.callback(None)
        finally:
            self.loaded_gif_signal.disconnect()

    def handle_animated_avif(self, file_name):
        from PIL import Image
        image = Image.open(file_name)

        if image.mode != "RGBA":
            frames = [image.seek(i) or image.convert("RGBA") for i in range(image.n_frames)]
        else:
            frames = [image.seek(i) or image.copy() for i in range(image.n_frames)]

        with BytesIO() as gif_buffer:
            frames[0].save(
                gif_buffer,
                format="WEBP",
                save_all=True,
                append_images=frames[1:],
                method=0,
                duration=max(10, image.info.get('duration', 100) - 5),
                loop=0
            )
            gif_data = gif_buffer.getvalue()

        self.loaded_gif_signal.emit(("gif_data", gif_data))
        return
