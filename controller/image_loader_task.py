import os
from PyQt5.QtCore import QRunnable, pyqtSlot
from PyQt5.QtGui import QPixmap
from io import BytesIO
import requests


class ImageLoaderTask(QRunnable):
    cache = {}

    def __init__(self, image_url, callback, save_folder="cache", only_cache_file=False):
        super().__init__()
        self.image_url = image_url
        self.callback = callback
        self.save_folder = save_folder
        self.only_cache_file = only_cache_file

    @pyqtSlot()
    def run(self):
        try:
            if self.only_cache_file:
                file_name = os.path.join(self.save_folder, os.path.basename(self.image_url))
                if os.path.exists(file_name):
                    pixmap = QPixmap(file_name)
                    if not pixmap.isNull():
                        ImageLoaderTask.cache[self.image_url] = pixmap
                        self.callback(file_name)
                        return
                else:
                    self.callback(None)
                    return

            if self.image_url in ImageLoaderTask.cache:
                pixmap = ImageLoaderTask.cache[self.image_url]
                self.callback(pixmap)
                return

            file_name = None
            if self.save_folder:
                os.makedirs(self.save_folder, exist_ok=True)
                file_name = os.path.join(
                    self.save_folder, os.path.basename(self.image_url)
                )

                if os.path.exists(file_name):
                    pixmap = QPixmap(file_name)
                    if not pixmap.isNull():
                        ImageLoaderTask.cache[self.image_url] = pixmap
                        self.callback(pixmap)
                        return

            response = requests.get(self.image_url)
            response.raise_for_status()
            image_data = BytesIO(response.content)

            if file_name:
                with open(file_name, "wb") as file:
                    file.write(response.content)

            pixmap = QPixmap()
            if pixmap.loadFromData(image_data.getbuffer()):
                ImageLoaderTask.cache[self.image_url] = pixmap
                self.callback(pixmap)
        except Exception as e:
            print(f"Error loading image: {e}")
            if self.callback:
                self.callback(None)

