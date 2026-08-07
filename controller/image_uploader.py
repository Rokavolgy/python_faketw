import io
import logging
import os
import threading
import uuid

from PIL import Image, ImageOps
from PySide6.QtCore import Signal, Slot, QObject

from controller.profiler import track_execution_time
from controller.supabase_storage_client import SupabaseStorageClient
from controller.user_session import UserSession
from modal.constants import Constants

logger = logging.getLogger(__name__)


class ImageUploaderSignals(QObject):
    _success_ready = Signal(str)
    _failure_ready = Signal(str)
    success_signal = Signal(str)
    failure_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self._success_ready.connect(self._deliver_success)
        self._failure_ready.connect(self._deliver_failure)

    @Slot(str)
    def _deliver_success(self, message):
        self.success_signal.emit(message)

    @Slot(str)
    def _deliver_failure(self, message):
        self.failure_signal.emit(message)


class ImageUploader:
    """Class to handle image uploading and compression"""

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
                    logger.debug("Reducing quality to %s and speed to %s", quality, speed)
                buffer = self.gif_to_avif_buffer(image_path, quality=quality, speed=speed,
                                                 drop_every_second_frame=drop_every_second_frame)
                if not drop_every_second_frame and quality < 40:
                    quality = quality + 30
                    drop_every_second_frame = True
                    logger.debug("Dropping every second frame to reduce AVIF size")

            else:
                if buffer.getbuffer().nbytes > self.MAX_FILE_SIZE:
                    logger.warning("AVIF converted from GIF is still too large")
                    raise RuntimeError("AVIF is too large after compression")
                return buffer

        if isinstance(img, Image.Image):
            img = ImageOps.exif_transpose(img)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

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
            logger.debug("Reducing image dimensions to fit the upload size limit")
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
        if output.tell() > self.MAX_FILE_SIZE:
            raise RuntimeError("Image is too large after compression")
        output.seek(0)
        return output

    @staticmethod
    def _destination(destination: str, recipient_id: str | None = None):
        session = UserSession()
        if not session.user_id:
            raise RuntimeError("A Firebase login is required")
        object_id = str(uuid.uuid4())
        if destination == "message":
            if not recipient_id:
                raise ValueError("A recipient is required for message images")
            first_uid, second_uid = sorted((session.user_id, recipient_id))
            return (
                Constants.MESSAGE_IMAGE_BUCKET,
                f"direct/{first_uid}/{second_uid}/{session.user_id}/{object_id}",
            )
        folder = "post-images" if destination == "post" else "user-images"
        return Constants.PUBLIC_IMAGE_BUCKET, f"{folder}/{session.user_id}/{object_id}"

    def upload_image(
            self,
            image_path: str,
            compress: bool = True,
            destination: str = "profile",
            recipient_id: str | None = None,
    ) -> None:
        """
        Upload an image file to Supabase storage

        Args:
            image_path: Path to the image file
            compress: Whether to compress the image before uploading only compresses to 512kb!
        """

        def upload_task():
            try:
                if compress:
                    raw_data = self.compress_image(image_path).getvalue()
                    is_avif_data = len(raw_data) >= 12 and raw_data[4:8] == b"ftyp"
                    extension = "avif" if is_avif_data else "webp"
                    content_type = f"image/{extension}"
                else:
                    with open(image_path, "rb") as image_file:
                        raw_data = image_file.read()
                    extension = os.path.splitext(image_path)[1].lower().lstrip(".")
                    content_type = f"image/{'jpeg' if extension in ('jpg', 'jpeg') else extension}"

                bucket, path_without_extension = self._destination(destination, recipient_id)
                path = f"{path_without_extension}.{extension}"
                SupabaseStorageClient().upload(bucket, path, raw_data, content_type)
                logger.info("Image upload completed")
                self.signals._success_ready.emit(path)
            except Exception as exc:
                logger.exception("Image upload failed")
                self.signals._failure_ready.emit(str(exc))

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
