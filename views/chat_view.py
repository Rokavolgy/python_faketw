import os
import weakref

from PySide6.QtCore import Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QPalette, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from controller.firebase_client import fetch_user_info
from controller.firestore_listener import FirestoreListener
from controller.image_loader_task import ImageLoaderTask
from controller.image_uploader import ImageUploader
from controller.messaging_controller import (
    ensure_direct_conversation, mark_conversation_read, send_image_message,
    send_text_message,
)
from controller.supabase_storage_client import SupabaseStorageClient
from controller.user_session import UserSession
from views.image_preview_window import ImagePreviewWindow
from widgets.clickable_labels import ClickableImageLabel


class MessageBubble(QWidget):
    def __init__(
            self, message, own_message, thread_pool, preview_requested=None, sender_name="User"
    ):
        super().__init__()
        self._full_pixmap = None
        self._preview_requested = preview_requested
        self._sender_name = sender_name
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 3, 8, 3)
        bubble = QWidget()
        bubble.setMaximumWidth(480)
        background, text_color = self._bubble_colors(own_message)
        bubble.setStyleSheet(
            f"background: {background}; color: {text_color}; "
            "border-radius: 4px;"
        )
        content = QVBoxLayout(bubble)
        content.setContentsMargins(10, 8, 10, 8)
        content.setSpacing(0)

        if message.type == "image" and message.storagePath:
            image_label = ClickableImageLabel("message-image", sender_name)
            image_label.setText("Loading image...")
            image_label.setAlignment(Qt.AlignCenter)
            image_label.setMinimumSize(220, 160)
            image_label.setStyleSheet(f"color: {text_color};")
            image_label.setCursor(Qt.PointingHandCursor)
            image_label.clicked.connect(lambda *_args: self.request_image_preview())
            content.addWidget(image_label)
            storage = SupabaseStorageClient()
            url = storage.authenticated_url(message.storageBucket, message.storagePath)

            def apply_image(pixmap):
                try:
                    if pixmap and not pixmap.isNull():
                        self._full_pixmap = QPixmap(pixmap)
                        image_label.setPixmap(
                            pixmap.scaled(
                                420, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation
                            )
                        )
                        image_label.setText("")
                    else:
                        image_label.setText("Image unavailable")
                except RuntimeError:
                    pass

            thread_pool.start(
                ImageLoaderTask(
                    url,
                    apply_image,
                    save_folder=os.path.join("cache", "message-images"),
                    response_getter=lambda _url: storage.download(
                        message.storageBucket, message.storagePath
                    ),
                )
            )

        if message.text:
            text = QLabel()
            text.setTextFormat(Qt.PlainText)
            text.setText(message.text)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text.setStyleSheet(f"color: {text_color};")
            content.addWidget(text)

        if message.createdAt and hasattr(message.createdAt, "strftime"):
            timestamp = QLabel(message.createdAt.strftime("%H:%M"))
            timestamp.setAlignment(Qt.AlignRight)
            timestamp.setStyleSheet(f"color: {text_color}; font-size: 8pt;")
            content.addWidget(timestamp)

        if own_message:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()

    def request_image_preview(self):
        if self._preview_requested and self._full_pixmap and not self._full_pixmap.isNull():
            self._preview_requested(QPixmap(self._full_pixmap), self._sender_name)

    def _bubble_colors(self, own_message):
        window_color = self.palette().color(QPalette.ColorRole.Window)
        dark_mode = window_color.lightness() < 128
        if dark_mode:
            return ("#164e63", "#f8fafc") if own_message else ("#374151", "#f9fafb")
        return ("#d9efff", "#102a43") if own_message else ("#eeeeee", "#1f2937")


class ChatView(QMainWindow):
    def __init__(self, other_user_id, parent_window=None):
        super().__init__()
        self.other_user_id = other_user_id
        self.parent_window = parent_window
        self.thread_pool = QThreadPool.globalInstance()
        self.messages = {}
        self._image_previews = []
        self.selected_image_path = None
        self.pending_caption = ""
        self.conversation_id = ensure_direct_conversation(other_user_id)
        self.listener = FirestoreListener()
        self.listener.messageUpdatedSignal.connect(self.on_message_updated)
        self.listener.messageRemovedSignal.connect(self.on_message_removed)
        self.image_uploader = ImageUploader()
        self.image_uploader.signals.success_signal.connect(self.on_image_uploaded)
        self.image_uploader.signals.failure_signal.connect(self.on_image_upload_failed)
        self.read_timer = QTimer(self)
        self.read_timer.setSingleShot(True)
        self.read_timer.timeout.connect(self.mark_latest_read)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.rebuild_messages)
        self.init_ui()
        self.listener.subscribe_to_messages(self.conversation_id)

    def init_ui(self):
        profile = fetch_user_info(self.other_user_id) or {}
        name = profile.get("displayName") or profile.get("username") or "Conversation"
        self.conversation_name = name
        container = QWidget()
        container.setObjectName("chatRoot")
        container.setStyleSheet(
            "#chatRoot { background: palette(window); color: palette(window-text); }"
            "QScrollArea { border: none; background: palette(base); }"
            "QTextEdit { border: 1px solid palette(mid); border-radius: 10px; "
            "padding: 8px; background: palette(base); color: palette(text); }"
            "QPushButton#sendButton { background: palette(highlight); "
            "color: palette(highlighted-text); border: none; border-radius: 9px; "
            "padding: 8px 18px; font-weight: bold; }"
            "QPushButton#sendButton:disabled { background: palette(mid); }"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        header_widget = QFrame()
        header_widget.setFrameShape(QFrame.NoFrame)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 4)
        back_button = QPushButton("Back")
        back_button.setCursor(Qt.PointingHandCursor)
        back_button.clicked.connect(self.go_back)
        header.addWidget(back_button)
        title = QLabel()
        title.setTextFormat(Qt.PlainText)
        title.setText(name)
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        layout.addWidget(header_widget)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.messages_widget = QWidget()
        self.messages_widget.setStyleSheet("background: palette(base);")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(8, 10, 8, 10)
        self.messages_layout.setSpacing(2)
        self.messages_layout.addStretch()
        self.scroll.setWidget(self.messages_widget)
        layout.addWidget(self.scroll, 1)

        self.attachment_label = QLabel()
        self.attachment_label.setTextFormat(Qt.PlainText)
        self.attachment_label.setAlignment(Qt.AlignCenter)
        self.attachment_label.setVisible(False)
        layout.addWidget(self.attachment_label)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Write a message...")
        self.editor.setMaximumHeight(110)
        layout.addWidget(self.editor)

        buttons = QHBoxLayout()
        attach_button = QPushButton("Attach image")
        attach_button.setCursor(Qt.PointingHandCursor)
        attach_button.clicked.connect(self.select_image)
        buttons.addWidget(attach_button)
        self.remove_attachment_button = QPushButton("Remove attachment")
        self.remove_attachment_button.setCursor(Qt.PointingHandCursor)
        self.remove_attachment_button.clicked.connect(self.remove_attachment)
        self.remove_attachment_button.setVisible(False)
        buttons.addWidget(self.remove_attachment_button)
        buttons.addStretch()
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.clicked.connect(self.send)
        buttons.addWidget(self.send_button)
        layout.addLayout(buttons)
        self.setCentralWidget(container)

    @staticmethod
    def _message_sort_value(message):
        timestamp = message.createdAt
        return timestamp.timestamp() if hasattr(timestamp, "timestamp") else 0

    def rebuild_messages(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        current_user_id = UserSession().user_id
        for message in sorted(self.messages.values(), key=self._message_sort_value):
            own_message = message.senderId == current_user_id
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1,
                MessageBubble(
                    message,
                    own_message,
                    self.thread_pool,
                    preview_requested=self.open_image_preview,
                    sender_name="You" if own_message else self.conversation_name,
                ),
            )
        QTimer.singleShot(
            20,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ),
        )

    def open_image_preview(self, pixmap, sender_name):
        preview = ImagePreviewWindow("", sender_name)
        preview_ref = weakref.ref(preview)

        def release_preview(*_args):
            closed_preview = preview_ref()
            if closed_preview in self._image_previews:
                self._image_previews.remove(closed_preview)

        preview.destroyed.connect(release_preview)
        self._image_previews.append(preview)
        preview.set_pixmap(pixmap)
        preview.show()

    @Slot(object)
    def on_message_updated(self, message):
        self.messages[message.id] = message
        self.render_timer.start(0)

    @Slot(str)
    def on_message_removed(self, message_id):
        self.messages.pop(message_id, None)
        self.render_timer.start(0)

    def mark_latest_read(self):
        if self.messages:
            latest = max(self.messages.values(), key=self._message_sort_value)
            mark_conversation_read(self.conversation_id, latest.id)

    @Slot()
    def select_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach image", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.selected_image_path = path
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self.attachment_label.setText(f"Attached: {os.path.basename(path)}")
            else:
                self.attachment_label.setPixmap(
                    pixmap.scaled(360, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            self.attachment_label.setVisible(True)
            self.remove_attachment_button.setVisible(True)

    @Slot()
    def remove_attachment(self):
        self.selected_image_path = None
        self.attachment_label.clear()
        self.attachment_label.setVisible(False)
        self.remove_attachment_button.setVisible(False)

    @Slot()
    def send(self):
        text = self.editor.toPlainText().strip()
        if not text and not self.selected_image_path:
            return
        self.send_button.setEnabled(False)
        self.send_button.setText("Sending...")
        if self.selected_image_path:
            self.pending_caption = text
            self.image_uploader.upload_image(
                self.selected_image_path,
                destination="message",
                recipient_id=self.other_user_id,
            )
            return
        try:
            send_text_message(self.conversation_id, text)
            self.editor.clear()
        except Exception as exc:
            QMessageBox.warning(self, "Sending failed", str(exc))
        finally:
            self.finish_send()

    @Slot(str)
    def on_image_uploaded(self, storage_path):
        try:
            send_image_message(self.conversation_id, storage_path, self.pending_caption)
            self.editor.clear()
            self.selected_image_path = None
            self.pending_caption = ""
            self.attachment_label.clear()
            self.attachment_label.setVisible(False)
            self.remove_attachment_button.setVisible(False)
        except Exception as exc:
            QMessageBox.warning(self, "Sending failed", str(exc))
        finally:
            self.finish_send()

    @Slot(str)
    def on_image_upload_failed(self, error):
        QMessageBox.warning(self, "Upload failed", error)
        self.finish_send()

    def finish_send(self):
        self.send_button.setEnabled(True)
        self.send_button.setText("Send")

    @Slot()
    def go_back(self):
        self.cleanup()
        if self.parent_window:
            self.parent_window.show_messages_view(replace_current=self)

    def cleanup(self):
        self.listener.stop_listening()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
