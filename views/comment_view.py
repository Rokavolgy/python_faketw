from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QMessageBox, QPushButton, QTextEdit, QSizePolicy
)

from controller.comment_controller import fetch_post_comments, add_comment, delete_comment
from controller.firestore_listener import FirestoreListener
from controller.image_loader_task import ImageLoaderTask
from controller.post_controller import fetch_post_by_id
from controller.user_session import UserSession
from modal.comment import CommentData
from modal.constants import Constants
from widgets.clickable_labels import ClickableLabel
from widgets.post_display import format_timestamp
from widgets.post_widget import PostWidget
from widgets.virtualized_list import VirtualizedWidgetList


class DeleteCommentSignals(QObject):
    finished = Signal(str, bool)


class DeleteCommentTask(QRunnable):
    def __init__(self, post_id, comment_id):
        super().__init__()
        self.post_id = post_id
        self.comment_id = comment_id
        self.signals = DeleteCommentSignals()

    def run(self):
        success = delete_comment(self.post_id, self.comment_id)
        self.signals.finished.emit(self.comment_id, success)


class AddCommentSignals(QObject):
    finished = Signal(bool)


class AddCommentTask(QRunnable):
    def __init__(self, post_id, content):
        super().__init__()
        self.post_id = post_id
        self.content = content
        self.signals = AddCommentSignals()

    @Slot()
    def run(self):
        self.signals.finished.emit(add_comment(self.post_id, self.content))


class CommentWidget(QWidget):
    removeRequested = Signal(str)
    profileClicked = Signal(str)

    def __init__(self, comment_data, current_user_id=None):
        super().__init__()
        self.comment_data = comment_data
        self.current_user_id = current_user_id
        self.thread_pool = QThreadPool.globalInstance()
        self.remove_button = None
        self._disposed = False
        self._binding_generation = 0
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Comment header with user info
        header_layout = QHBoxLayout()

        # Profile pic
        self.profile_pic = ClickableLabel(self.comment_data.userId)
        self.profile_pic.setFixedSize(30, 30)
        self.profile_pic.setStyleSheet("background-color: lightgray; border-radius: 15px;")
        self.profile_pic.setToolTip("View profile")
        self.profile_pic.clicked.connect(self.profileClicked.emit)

        self._start_profile_image_load()

        header_layout.addWidget(self.profile_pic)

        # User info
        user_info_layout = QVBoxLayout()

        self.username_label = QLabel()
        self.username_label.setTextFormat(Qt.PlainText)
        self.username_label.setText(self.comment_data.userName)
        self.username_label.setFont(QFont("Wix Madefor Text", 10, QFont.Bold))
        self.time_label = QLabel(format_timestamp(self.comment_data.timestamp))
        self.time_label.setStyleSheet("color: gray; font-size: 8pt;")

        user_info_layout.addWidget(self.username_label)
        user_info_layout.addWidget(self.time_label)
        header_layout.addLayout(user_info_layout)
        header_layout.addStretch()

        self.remove_button = QPushButton("Remove")
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setToolTip("Remove comment")
        self.remove_button.setStyleSheet("""
            QPushButton {
                color: #b42318;
                background: transparent;
                border: none;
                padding: 4px 6px;
                font-size: 9pt;
            }
            QPushButton:hover { background-color: #fee4e2; }
            QPushButton:disabled { color: #999999; }
        """)
        self.remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self.comment_data.id)
        )
        self.remove_button.setVisible(
            self.current_user_id == self.comment_data.userId
        )
        header_layout.addWidget(self.remove_button)

        main_layout.addLayout(header_layout)

        # Comment content
        self.content_label = QLabel()
        self.content_label.setTextFormat(Qt.PlainText)
        self.content_label.setText(self.comment_data.content)
        self.content_label.setFont(QFont("Wix Madefor Text", 10))
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("margin: 5px 0 10px 35px;")
        main_layout.addWidget(self.content_label)

        # Separator
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #e0e0e0;")
        main_layout.addWidget(separator)

    def set_remove_pending(self, pending):
        if not self._disposed and self.remove_button:
            self.remove_button.setEnabled(not pending)
            self.remove_button.setText("Removing..." if pending else "Remove")

    def update_profile_image(self, pixmap):
        if self._disposed or pixmap is None:
            return
        scaled_pixmap = pixmap.scaled(
            30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.profile_pic.setPixmap(scaled_pixmap)

    def _start_profile_image_load(self):
        self.profile_pic.clear()
        if not self.comment_data.userProfilePicUrl:
            return
        generation = self._binding_generation
        image_url = Constants.STORAGE_URL + self.comment_data.userProfilePicUrl

        def apply(pixmap):
            if generation == self._binding_generation:
                self.update_profile_image(pixmap)

        self.thread_pool.start(ImageLoaderTask(image_url, apply))

    def prepare_for_reuse(self):
        self._binding_generation += 1
        self.profile_pic.clear()

    def bind_comment(self, comment_data):
        self.prepare_for_reuse()
        self.comment_data = comment_data
        self._disposed = False
        self.profile_pic.userId = comment_data.userId
        self.username_label.setText(comment_data.userName)
        self.time_label.setText(format_timestamp(comment_data.timestamp))
        self.content_label.setText(comment_data.content)
        self.remove_button.setVisible(
            self.current_user_id == comment_data.userId
        )
        self.set_remove_pending(False)
        self._start_profile_image_load()

    def cleanup_and_delete(self):
        if self._disposed:
            return
        self._disposed = True
        self._binding_generation += 1
        if self.remove_button:
            try:
                self.remove_button.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.profile_pic.clear()
        self.setParent(None)
        self.deleteLater()


class CommentView(QMainWindow):
    """View for displaying comments on a post"""
    commentPosted = Signal(object)
    profileRequested = Signal(str)

    def __init__(self, post_id=None, profile_data=None, parent_window=None):
        super().__init__()
        self.post_id = post_id
        self.parent_window = parent_window
        self.thread_pool = QThreadPool.globalInstance()
        self.post_data = None
        self.comments = []
        self.comments_label = None
        self.comments_list = None
        self.comment_edit = None
        self.post_button = None
        self.post_widget = None
        self.pending_comment_deletions = set()
        self._comment_task = None

        # Set up listener for real-time updates
        self.listener = FirestoreListener()
        self.listener.commentAddedSignal.connect(self.on_comment_added)
        self.listener.commentRemovedSignal.connect(self.on_comment_removed)

        if self.post_id:
            self.post_data = fetch_post_by_id(
                self.post_id, user_likes=UserSession().user_likes or []
            )
            self.comments = fetch_post_comments(self.post_id)

        self.init_ui()

        # Subscribe to comment updates
        if self.post_id:
            self.listener.subscribe_to_post_comments(self.post_id)

    def init_ui(self):
        self.setWindowTitle("Comments")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        # If we have post data, display the post first
        if self.post_data:
            # Display the original post
            self.post_widget = PostWidget(self.post_data, hide_buttons=True, lazy_media=False)
            self.post_widget.profileClicked.connect(self.profileRequested.emit)
            self.post_widget.setMaximumHeight(400)
            main_layout.addWidget(self.post_widget)

            # Add a label for comments section
            self.comments_label = QLabel()
            self.comments_label.setFont(QFont("Wix Madefor Text", 14, QFont.Bold))
            # self.update_comments_label()
            # main_layout.addWidget(self.comments_label)

            self.comments_list = VirtualizedWidgetList(
                widget_factory=self.create_comment_widget,
                key_for_item=lambda comment: comment.id,
                estimate_height=self.estimate_comment_height,
                widget_binder=self.bind_comment_widget,
                overscan_rows=3,
            )
            self.comments_list.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            self.comments_list.set_items(self.comments)
            main_layout.addWidget(self.comments_list)

            # Add comment input section
            comment_input_section = self.create_comment_input()
            main_layout.addWidget(comment_input_section)
        else:
            # If no post data, show message
            no_post_label = QLabel("Post not found or no comments available")
            no_post_label.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(no_post_label)
            back_button = QPushButton("Back to Feed")
            back_button.clicked.connect(self.go_back)
            main_layout.addWidget(back_button)

        # Back button


        self.setCentralWidget(main_widget)

    def create_comment_input(self):
        input_widget = QWidget()
        input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        input_layout = QVBoxLayout(input_widget)
        input_layout.addStretch()

        # Comment text edit
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("Write a comment...")
        self.comment_edit.setMaximumHeight(100)
        input_layout.addWidget(self.comment_edit)

        # Post button
        button_layout = QHBoxLayout()

        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.go_back)
        button_layout.addWidget(self.back_button)
        button_layout.addStretch()

        self.post_button = QPushButton("Post Comment")
        self.post_button.setCursor(Qt.PointingHandCursor)
        self.post_button.clicked.connect(self.post_comment)
        button_layout.addWidget(self.post_button)

        input_layout.addLayout(button_layout)

        return input_widget

    @Slot()
    def post_comment(self):
        comment_text = self.comment_edit.toPlainText().strip()
        if not comment_text:
            return

        user_session = UserSession()
        if not user_session.is_authenticated:
            QMessageBox.warning(self, "Authentication Required", "Please log in to post a comment.")
            return

        if self.post_button:
            self.post_button.setEnabled(False)
            self.post_button.setText("Posting...")

        self._comment_task = AddCommentTask(self.post_id, comment_text)
        self._comment_task.signals.finished.connect(self.on_comment_post_finished)
        self.thread_pool.start(self._comment_task)

    @Slot(bool)
    def on_comment_post_finished(self, success):
        if success:
            self.comment_edit.clear()
        else:
            QMessageBox.warning(self, "Comment Failed", "Failed to post comment.")

        if self.post_button:
            self.post_button.setEnabled(True)
            self.post_button.setText("Post Comment")
        self._comment_task = None

    @Slot(CommentData)
    def on_comment_added(self, comment_data):
        if comment_data.postId != self.post_id:
            return

        existing_index = next(
            (i for i, comment in enumerate(self.comments) if comment.id == comment_data.id),
            None,
        )
        if existing_index is not None:
            self.comments[existing_index] = comment_data
            if self.comments_list:
                self.comments_list.update_item(comment_data)
            return

        # Update comment count on post if available
        if self.post_data:
            self.post_data.commentsCount = (self.post_data.commentsCount or 0) + 1

        # Add to local comments list
        self.comments.append(comment_data)

        if self.comments_list:
            self.comments_list.insert_item(len(self.comments) - 1, comment_data)

        self.update_comments_label()

    @Slot(str)
    def on_comment_removed(self, comment_id):
        old_count = len(self.comments)
        self.comments = [
            comment for comment in self.comments if comment.id != comment_id
        ]
        if len(self.comments) != old_count:
            if self.post_data:
                self.post_data.commentsCount = max(
                    0, (self.post_data.commentsCount or 0) - 1
                )
            if self.comments_list:
                self.comments_list.remove_key(comment_id)
            self.update_comments_label()

    def create_comment_widget(self, comment):
        comment_widget = CommentWidget(comment, UserSession().user_id)
        comment_widget.removeRequested.connect(self.remove_comment)
        comment_widget.profileClicked.connect(self.profileRequested.emit)
        comment_widget.set_remove_pending(
            comment.id in self.pending_comment_deletions
        )
        return comment_widget

    def bind_comment_widget(self, widget, comment):
        widget.bind_comment(comment)
        widget.set_remove_pending(
            comment.id in self.pending_comment_deletions
        )

    @staticmethod
    def estimate_comment_height(comment, viewport_width):
        text_width = max(220, viewport_width - 80)
        characters_per_line = max(20, text_width // 8)
        content_lines = max(
            1,
            (len(comment.content or "") + characters_per_line - 1)
            // characters_per_line,
        )
        return 85 + min(content_lines, 10) * 20

    @Slot(str)
    def remove_comment(self, comment_id):
        user_session = UserSession()
        if (
                not user_session.is_authenticated
                or comment_id in self.pending_comment_deletions
        ):
            return

        answer = QMessageBox.question(
            self,
            "Remove Comment",
            "Remove this comment?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.pending_comment_deletions.add(comment_id)
        self.set_comment_remove_pending(comment_id, True)
        task = DeleteCommentTask(self.post_id, comment_id)
        task.signals.finished.connect(self.on_comment_delete_finished)
        self.thread_pool.start(task)

    @Slot(str, bool)
    def on_comment_delete_finished(self, comment_id, success):
        self.pending_comment_deletions.discard(comment_id)
        if success:
            self.on_comment_removed(comment_id)
            return

        self.set_comment_remove_pending(comment_id, False)
        QMessageBox.warning(self, "Remove Failed", "Failed to remove comment.")

    def set_comment_remove_pending(self, comment_id, pending):
        if not self.comments_list:
            return
        widget = self.comments_list.widget_for_key(comment_id)
        if widget:
            widget.set_remove_pending(pending)

    def update_comments_label(self):
        if self.comments_label:
            self.comments_label.setText(f"Comments ({len(self.comments)})")

    @Slot()
    def go_back(self):
        if self.parent_window and hasattr(self.parent_window, "stacked_widget"):
            self.parent_window.stacked_widget.setCurrentIndex(0)
            self.parent_window.stacked_widget.removeWidget(self)
            self.cleanup()
            self.setParent(None)
            self.deleteLater()
        else:
            self.close()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self):
        if hasattr(self, "listener"):
            self.listener.stop_listening()
            try:
                self.listener.commentAddedSignal.disconnect(self.on_comment_added)
                self.listener.commentRemovedSignal.disconnect(self.on_comment_removed)
            except Exception:
                pass

        if self.post_widget:
            self.post_widget.cleanup_and_delete()
            self.post_widget = None

        if self.comments_list:
            self.comments_list.clear_items()
            self.comments_list = None
        self.comments = []
        self.pending_comment_deletions.clear()
        self._comment_task = None
