from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea,
    QMessageBox, QPushButton, QTextEdit, QSizePolicy
)

from controller.comment_controller import fetch_post_comments, add_comment, delete_comment
from controller.firestore_listener import FirestoreListener
from controller.image_loader_task import ImageLoaderTask
from controller.post_controller import fetch_post_by_id
from controller.user_session import UserSession
from modal.constants import Constants
from widgets.post_widget import PostWidget


class DeleteCommentSignals(QObject):
    finished = Signal(str, bool)


class DeleteCommentTask(QRunnable):
    def __init__(self, post_id, comment_id, user_id):
        super().__init__()
        self.post_id = post_id
        self.comment_id = comment_id
        self.user_id = user_id
        self.signals = DeleteCommentSignals()

    def run(self):
        success = delete_comment(self.post_id, self.comment_id, self.user_id)
        self.signals.finished.emit(self.comment_id, success)


# noinspection PyAttributeOutsideInit
def update_image(label, pixmap, height, width):
    scaled_pixmap = pixmap.scaled(height, width, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    label.setPixmap(scaled_pixmap)


class CommentWidget(QWidget):
    removeRequested = Signal(str)

    def __init__(self, comment_data, current_user_id=None):
        super().__init__()
        self.comment_data = comment_data
        self.current_user_id = current_user_id
        self.thread_pool = QThreadPool.globalInstance()
        self.remove_button = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Comment header with user info
        header_layout = QHBoxLayout()

        # Profile pic
        self.profile_pic = QLabel()
        self.profile_pic.setFixedSize(30, 30)
        self.profile_pic.setStyleSheet("background-color: lightgray; border-radius: 15px;")

        if self.comment_data.userProfilePicUrl:
            image_url = Constants.STORAGE_URL + self.comment_data.userProfilePicUrl
            task = ImageLoaderTask(
                image_url,
                lambda pixmap: update_image(self.profile_pic, pixmap, 30, 30),
            )
            self.thread_pool.start(task)

        header_layout.addWidget(self.profile_pic)

        # User info
        user_info_layout = QVBoxLayout()

        username_label = QLabel(self.comment_data.userName)
        username_label.setFont(QFont("Wix Madefor Text", 10, QFont.Bold))

        time_str = "Unknown date"
        if self.comment_data.timestamp and hasattr(self.comment_data.timestamp, "year"):
            from datetime import datetime
            time_str = datetime.strftime(self.comment_data.timestamp, "%Y-%m-%d %H:%M")

        time_label = QLabel(time_str)
        time_label.setStyleSheet("color: gray; font-size: 8pt;")

        user_info_layout.addWidget(username_label)
        user_info_layout.addWidget(time_label)
        header_layout.addLayout(user_info_layout)
        header_layout.addStretch()

        if self.current_user_id == self.comment_data.userId:
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
            header_layout.addWidget(self.remove_button)

        main_layout.addLayout(header_layout)

        # Comment content
        content_label = QLabel(self.comment_data.content)
        content_label.setFont(QFont("Wix Madefor Text", 10))
        content_label.setWordWrap(True)
        content_label.setStyleSheet("margin: 5px 0 10px 35px;")
        main_layout.addWidget(content_label)

        # Separator
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #e0e0e0;")
        main_layout.addWidget(separator)

    def set_remove_pending(self, pending):
        if self.remove_button:
            self.remove_button.setEnabled(not pending)
            self.remove_button.setText("Removing..." if pending else "Remove")


class CommentView(QMainWindow):
    """View for displaying comments on a post"""
    commentPosted = Signal(object)

    def __init__(self, post_id=None, profile_data=None, parent_window=None):
        super().__init__()
        self.post_id = post_id
        self.parent_window = parent_window
        self.thread_pool = QThreadPool.globalInstance()
        self.post_data = None
        self.comments = []
        self.comments_label = None
        self.comments_layout = None
        self.comment_edit = None
        self.post_button = None
        self.post_widget = None
        self.pending_comment_deletions = set()

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
            self.post_widget.setMaximumHeight(400)
            main_layout.addWidget(self.post_widget)

            # Add a label for comments section
            self.comments_label = QLabel()
            self.comments_label.setFont(QFont("Wix Madefor Text", 14, QFont.Bold))
            # self.update_comments_label()
            # main_layout.addWidget(self.comments_label)

            # Add scrollable comments section
            comments_scroll = QScrollArea()
            comments_scroll.setWidgetResizable(True)
            comments_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            comments_container = QWidget()
            self.comments_layout = QVBoxLayout(comments_container)

            # Add all comments
            for comment in self.comments:
                self.comments_layout.addWidget(self.create_comment_widget(comment))

            self.comments_layout.addStretch()
            comments_scroll.setWidget(comments_container)
            main_layout.addWidget(comments_scroll)

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
        # self.post_button.setStyleSheet("""
        #     QPushButton {
        #         background-color: #1DA1F2;
        #         color: white;
        #         border-radius: 15px;
        #         padding: 8px 16px;
        #         font-weight: bold;
        #     }
        #     QPushButton:hover {
        #         background-color: #0D91E2;
        #     }
        # """)
        self.post_button.clicked.connect(self.post_comment)
        button_layout.addWidget(self.post_button)

        input_layout.addLayout(button_layout)

        return input_widget

    def post_comment(self):
        comment_text = self.comment_edit.toPlainText().strip()
        if not comment_text:
            return

        user_session = UserSession()
        if not user_session.is_authenticated:
            QMessageBox.warning(self, "Authentication Required", "Please log in to post a comment.")
            return

        profile_data = user_session.profile_data
        user_name = profile_data.displayName if profile_data else "Unknown User"
        profile_pic_url = profile_data.profileImageUrl if profile_data else ""

        if self.post_button:
            self.post_button.setEnabled(False)
            self.post_button.setText("Posting...")

        success = add_comment(
            self.post_id,
            user_session.user_id,
            user_name,
            profile_pic_url,
            comment_text,
        )

        if success:
            self.comment_edit.clear()
        else:
            QMessageBox.warning(self, "Comment Failed", "Failed to post comment.")

        if self.post_button:
            self.post_button.setEnabled(True)
            self.post_button.setText("Post Comment")

    def on_comment_added(self, comment_data):
        if comment_data.postId != self.post_id:
            return

        existing_index = next(
            (i for i, comment in enumerate(self.comments) if comment.id == comment_data.id),
            None,
        )
        if existing_index is not None:
            self.comments[existing_index] = comment_data
            self.rebuild_comments()
            return

        # Update comment count on post if available
        if self.post_data:
            self.post_data.commentsCount = (self.post_data.commentsCount or 0) + 1

        # Add to local comments list
        self.comments.append(comment_data)

        # Add comment widget to UI
        comment_widget = self.create_comment_widget(comment_data)
        self.comments_layout.insertWidget(self.comments_layout.count() - 1, comment_widget)

        self.update_comments_label()

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
            self.rebuild_comments()

    def create_comment_widget(self, comment):
        comment_widget = CommentWidget(comment, UserSession().user_id)
        comment_widget.removeRequested.connect(self.remove_comment)
        return comment_widget

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
        task = DeleteCommentTask(self.post_id, comment_id, user_session.user_id)
        task.signals.finished.connect(self.on_comment_delete_finished)
        self.thread_pool.start(task)

    def on_comment_delete_finished(self, comment_id, success):
        self.pending_comment_deletions.discard(comment_id)
        if success:
            self.on_comment_removed(comment_id)
            return

        self.set_comment_remove_pending(comment_id, False)
        QMessageBox.warning(self, "Remove Failed", "Failed to remove comment.")

    def set_comment_remove_pending(self, comment_id, pending):
        if not self.comments_layout:
            return
        for index in range(self.comments_layout.count()):
            widget = self.comments_layout.itemAt(index).widget()
            if (
                    isinstance(widget, CommentWidget)
                    and widget.comment_data.id == comment_id
            ):
                widget.set_remove_pending(pending)
                return

    def rebuild_comments(self):
        if not self.comments_layout:
            return

        for i in reversed(range(self.comments_layout.count())):
            item = self.comments_layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, CommentWidget):
                self.comments_layout.removeWidget(widget)
                widget.deleteLater()

        for comment in self.comments:
            comment_widget = self.create_comment_widget(comment)
            self.comments_layout.insertWidget(
                self.comments_layout.count() - 1, comment_widget
            )
        self.update_comments_label()

    def update_comments_label(self):
        if self.comments_label:
            self.comments_label.setText(f"Comments ({len(self.comments)})")

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

        self.comments = []
        self.pending_comment_deletions.clear()
        self.comments_layout = None
