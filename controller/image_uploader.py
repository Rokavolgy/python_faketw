import io
import os
import threading
from datetime import datetime

import requests
from PIL import Image
from PySide6.QtCore import Signal, QObject

from controller.profiler import track_execution_time
from modal.constants import Constants


class ImageUploaderSignals(QObject):
    success_signal = Signal(str)
    failure_signal = Signal(str)

    def __init__(self):
        super().__init__()


class ImageUploader:
    """Class to handle image uploading and compression"""

    UPLOAD_URL = Constants.UPLOAD_URL
    STORAGE_URL = Constants.STORAGE_URL
    MAX_FILE_SIZE = Constants.MAX_FILE_SIZE

    def __init__(self):
        self.signals = ImageUploaderSignals()

    def get_file_url(self, file_name: str) -> str:
        return self.STORAGE_URL + file_name

    def compress_image(
            self, image_path: str, max_size: tuple = (1200, 1200)
    ) -> io.BytesIO:

        """
        Compress an image file until it's below MAX_FILE_SIZE

        Args:
            image_path: Path to the image file
            max_size: Maximum dimensions (width, height)

        Returns:
            BytesIO object containing the compressed image
        """
        img = Image.open(image_path)
        img_format = os.path.splitext(image_path)[1][1:].upper()

        img_format = "WEBP"  # webp lesz és xd
        if img.format == "GIF" and getattr(img, "is_animated", True):
            from PIL.features import check
            support = check('avif')
            if not support or support is None:
                raise RuntimeError("AVIF support is not available")

            quality = 85
            speed = 7
            drop_every_second_frame = False
            # some basic algo
            buffer = self.gif_to_avif_buffer(image_path, quality=quality, speed=speed,
                                             drop_every_second_frame=drop_every_second_frame)
            while buffer.getbuffer().nbytes > self.MAX_FILE_SIZE and quality > 30:
                over_with = self.MAX_FILE_SIZE - buffer.getbuffer().nbytes
                quality -= max(5, abs(int(12 * (over_with / 350000))))
                quality = min(100, max(quality, 22))
                if quality < 50:
                    speed = 4
                    print("Reducing quality to", quality, "and speed to", speed)
                buffer = self.gif_to_avif_buffer(image_path, quality=quality, speed=speed,
                                                 drop_every_second_frame=drop_every_second_frame)
                if not drop_every_second_frame and quality < 40:
                    quality = quality + 30
                    drop_every_second_frame = True
                    print("Dropping every second frame to reduce size")

            else:
                if buffer.getbuffer().nbytes > self.MAX_FILE_SIZE:
                    print("AVIF (converting from GIF) is still too large after compression, upload unsuccessful")
                    self.signals.failure_signal.emit("AVIF is too large after compression")
                    raise RuntimeError("AVIF is too large after compression")
                return buffer

        quality = 95
        current_size = float("inf")

        while current_size > self.MAX_FILE_SIZE and quality > 60:
            output = io.BytesIO()
            img.save(output, format=img_format, quality=quality, optimize=True)
            current_size = output.tell()
            output.seek(0)

            if current_size > self.MAX_FILE_SIZE:
                # faster quality drop if file is still too big
                if current_size - self.MAX_FILE_SIZE > 320000:
                    quality -= 15
                else:
                    quality -= 5
            else:
                break

        if current_size > self.MAX_FILE_SIZE:
            print("Reducing image dimensions to fit within size limit")
            reduction_factor = 0.9
            while current_size > self.MAX_FILE_SIZE and reduction_factor > 0.5:
                new_dimensions = (
                    int(img.width * reduction_factor),
                    int(img.height * reduction_factor),
                )
                resized_img = img.resize(new_dimensions, Image.LANCZOS)

                output = io.BytesIO()
                resized_img.save(
                    output, format=img_format, quality=quality, optimize=True
                )
                current_size = output.tell()
                output.seek(0)

                if current_size <= self.MAX_FILE_SIZE:
                    img = resized_img
                    break

                reduction_factor -= 0.1

        output = io.BytesIO()
        img.save(output, format=img_format, quality=quality, optimize=True)
        output.seek(0)
        return output

    def upload_image(self, image_path: str, compress: bool = True) -> None:
        """
        Upload an image file to Supabase storage

        Args:
            image_path: Path to the image file
            on_success: Signal. self.signals for success (takes image URL as parameter)
            on_failure: Signal. self.signals for failure (takes error message as parameter)
            compress: Whether to compress the image before uploading only compresses to 512kb!
        """

        def upload_task():

            current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            file_name = "JPEG_" + current_datetime + ".dat"
            if compress:
                file_data = self.compress_image(image_path)
                files = {"file": (file_name, file_data, "image/jpeg")}
            else:
                files = {"file": (file_name, open(image_path, "rb"))}

            response = requests.post(self.UPLOAD_URL, files=files)

            if response.status_code == 200:
                print("Uploaded: " + str(response.text))
                self.signals.success_signal.emit(response.text)
            else:
                error_msg = f"Server error: {response.status_code}, {response.text}"
                self.signals.failure_signal.emit(error_msg)

        thread = threading.Thread(target=upload_task)
        thread.daemon = True
        thread.start()

    @track_execution_time
    def gif_to_avif_buffer(self, image_path: str, quality: int = 90, speed: int = 5,
                           drop_every_second_frame: bool = False) -> io.BytesIO:
        """
        Convert an animated GIF to AVIF format and return it as a BytesIO buffer.

        Args:
            image_path: Path to the GIF file.
            quality: Quality of the AVIF output (default is 90).
            drop_every_second_frame: Whether to drop every second frame.

        Returns:
            BytesIO object containing the AVIF image.
        """
        img = Image.open(image_path)
        frames = []
        durations = []

        if drop_every_second_frame:
            # dropping frames
            for frame in range(0, img.n_frames, 2):
                img.seek(frame)
                frames.append(img.convert("RGBA"))
                duration = img.info.get('duration', 100)
                durations.append(duration)
        else:
            # Keep all frames and their durations
            for frame in range(img.n_frames):
                img.seek(frame)
                frames.append(img.convert("RGBA"))
                duration = img.info.get('duration', 100)

                durations.append(duration)
        output = io.BytesIO()
        frames[0].save(
            output,
            format="AVIF",
            append_images=frames[1:],
            quality=quality,
            speed=speed,
            duration=durations,
            loop=img.info.get('loop', 0)
        )
        output.seek(0)
        return output
