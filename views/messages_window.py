from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton,
    QVBoxLayout, QWidget,
)

from controller.firebase_client import fetch_user_info, get_db
from controller.firestore_listener import FirestoreListener
from controller.user_session import UserSession


class ConversationItemWidget(QWidget):
    def __init__(self, name, preview, timestamp=None, unread=False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        avatar = QLabel()
        avatar.setTextFormat(Qt.PlainText)
        avatar.setText((name[:1] or "?").upper())
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(44, 44)
        avatar.setStyleSheet(
            "background: palette(highlight); color: palette(highlighted-text); "
            "border-radius: 22px; font-size: 15pt; font-weight: bold;"
        )
        layout.addWidget(avatar)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        self.name_label = QLabel()
        self.name_label.setTextFormat(Qt.PlainText)
        self.name_label.setText(name)
        name_font = QFont(self.name_label.font())
        name_font.setBold(unread)
        self.name_label.setFont(name_font)
        text_layout.addWidget(self.name_label)

        self.preview_label = QLabel()
        self.preview_label.setTextFormat(Qt.PlainText)
        self.preview_label.setText(preview[:100])
        self.preview_label.setForegroundRole(QPalette.PlaceholderText)
        text_layout.addWidget(self.preview_label)
        layout.addLayout(text_layout, 1)

        meta_layout = QVBoxLayout()
        meta_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_label = QLabel(self._format_time(timestamp))
        time_label.setForegroundRole(QPalette.PlaceholderText)
        meta_layout.addWidget(time_label, 0, Qt.AlignRight)
        if unread:
            unread_label = QLabel("●")
            unread_label.setStyleSheet("color: palette(highlight); font-size: 12pt;")
            unread_label.setToolTip("Unread conversation")
            meta_layout.addWidget(unread_label, 0, Qt.AlignRight)
        layout.addLayout(meta_layout)

    @staticmethod
    def _format_time(timestamp):
        if not isinstance(timestamp, datetime):
            return ""
        now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
        return timestamp.strftime("%H:%M" if timestamp.date() == now.date() else "%b %d")


class MessagesWindow(QMainWindow):
    chatRequested = Signal(str)

    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        self.conversations = {}
        self.listener = FirestoreListener()
        self.listener.conversationUpdatedSignal.connect(self.on_conversation_updated)
        self.listener.conversationRemovedSignal.connect(self.on_conversation_removed)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.rebuild_list)
        self.init_ui()
        self.listener.subscribe_to_conversations(UserSession().user_id)

    def init_ui(self):
        container = QWidget()
        container.setObjectName("messagesRoot")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel("Messages")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)
        self.empty_label = QLabel("No conversations yet. Open a profile and choose Message.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setForegroundRole(QPalette.PlaceholderText)
        layout.addWidget(self.empty_label)
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet(
            "QListWidget { border: none; background: transparent; outline: none; }"
            "QListWidget::item { border-radius: 10px; }"
            "QListWidget::item:hover { background: palette(midlight); }"
            "QListWidget::item:selected { background: palette(highlight); "
            "color: palette(highlighted-text); }"
        )
        self.list_widget.itemClicked.connect(self.open_item)
        layout.addWidget(self.list_widget, 1)
        back_button = QPushButton("Back to Feed")
        back_button.setCursor(Qt.PointingHandCursor)
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
        self.setCentralWidget(container)

    @staticmethod
    def _sort_value(conversation):
        timestamp = conversation.updatedAt
        return timestamp.timestamp() if hasattr(timestamp, "timestamp") else 0

    def rebuild_list(self):
        self.list_widget.clear()
        current_user_id = UserSession().user_id
        conversations = sorted(
            self.conversations.values(), key=self._sort_value, reverse=True
        )
        for conversation in conversations:
            other_user_id = conversation.other_user_id(current_user_id)
            profile = fetch_user_info(other_user_id) or {}
            name = profile.get("displayName") or profile.get("username") or "Unknown user"
            preview = conversation.lastMessagePreview or "Start a conversation"
            unread = self.is_unread(conversation, current_user_id)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, other_user_id)
            item.setSizeHint(QSize(0, 68))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(
                item,
                ConversationItemWidget(
                    name,
                    preview,
                    timestamp=conversation.lastMessageAt or conversation.updatedAt,
                    unread=unread,
                ),
            )
        self.empty_label.setVisible(not conversations)
        self.list_widget.setVisible(bool(conversations))

    @staticmethod
    def is_unread(conversation, current_user_id):
        if not conversation.lastSenderId or conversation.lastSenderId == current_user_id:
            return False
        read_doc = get_db().collection("conversations").document(
            conversation.id
        ).collection("readStates").document(current_user_id).get()
        if not read_doc.exists:
            return True
        last_read = read_doc.to_dict().get("lastReadAt")
        last_message = conversation.lastMessageAt
        if not hasattr(last_read, "timestamp") or not hasattr(last_message, "timestamp"):
            return True
        return last_message.timestamp() > last_read.timestamp()

    @Slot(object)
    def on_conversation_updated(self, conversation):
        self.conversations[conversation.id] = conversation
        self.render_timer.start(50)

    @Slot(str)
    def on_conversation_removed(self, conversation_id):
        self.conversations.pop(conversation_id, None)
        self.render_timer.start(50)

    @Slot(QListWidgetItem)
    def open_item(self, item):
        other_user_id = item.data(Qt.UserRole)
        if other_user_id:
            self.chatRequested.emit(other_user_id)

    @Slot()
    def go_back(self):
        self.cleanup()
        if self.parent_window:
            self.parent_window.stacked_widget.setCurrentWidget(self.parent_window.posts_view)
            self.parent_window.stacked_widget.removeWidget(self)
            self.deleteLater()

    def cleanup(self):
        self.listener.stop_listening()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
