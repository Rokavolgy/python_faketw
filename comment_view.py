from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea,
    QPushButton, QTextEdit, QSizePolicy
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThreadPool, Signal

from controller.image_loader_task import ImageLoaderTask
from controller.firestore import FirestoreListener, fetch_post_by_id
from controller.user_session import UserSession
from modal.constants import Constants
from post_widget import PostWidget


class CommentWidget(QWidget):
    def __init__(self, comment_data):
        super().__init__()
        self.comment_data = comment_data
        self.thread_pool = QThreadPool()
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
                lambda pixmap: self.update_image(self.profile_pic, pixmap, 30, 30),
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

    def update_image(self, label, pixmap, height, width):
        scaled_pixmap = pixmap.scaled(height, width, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled_pixmap)


class CommentView(QMainWindow):
    commentPosted = Signal(object)

    def __init__(self, post_id=None, profile_data=None, parent_window=None):
        super().__init__()
        self.post_id = post_id
        self.parent_window = parent_window
        self.thread_pool = QThreadPool()
        self.post_data = None
        self.comments = []

        self.listener = FirestoreListener()
        #self.listener.commentAddedSignal.connect(self.on_comment_added)

        if self.post_id:
            self.post_data = fetch_post_by_id(self.post_id)

        self.init_ui()

        #if self.post_id:
        #    self.listener.subscribe_to_post_comments(self.post_id)

    def init_ui(self):
        self.setWindowTitle("Comments")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)


        if self.post_data:
            # original post
            post_widget = PostWidget(self.post_data, hide_buttons=True)
            post_widget.setMaximumHeight(400)
            main_layout.addWidget(post_widget)

            # scrollable comments section
            comments_label = QLabel(f"Comments ({len(self.comments)})")
            comments_label.setFont(QFont("Wix Madefor Text", 14, QFont.Bold))
            main_layout.addWidget(comments_label)


            comments_scroll = QScrollArea()
            comments_scroll.setWidgetResizable(True)
            comments_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            comments_container = QWidget()
            self.comments_layout = QVBoxLayout(comments_container)


            for comment in self.comments:
                comment_widget = CommentWidget(comment)
                self.comments_layout.addWidget(comment_widget)

            self.comments_layout.addStretch()
            comments_scroll.setWidget(comments_container)
            main_layout.addWidget(comments_scroll)

            # input
            comment_input_section = self.create_comment_input()
            main_layout.addWidget(comment_input_section)
        else:
            # error
            no_post_label = QLabel("Post not found or no comments available")
            no_post_label.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(no_post_label)

        # back
        back_button = QPushButton("Back to Feed")
        back_button.clicked.connect(self.go_back)
        main_layout.addWidget(back_button)

        self.setCentralWidget(main_widget)

    def create_comment_input(self):
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)

        # Comment text edit
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("Write a comment...")
        self.comment_edit.setMaximumHeight(100)
        input_layout.addWidget(self.comment_edit)

        # Post button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        post_button = QPushButton("Post Comment")
        post_button.setCursor(Qt.PointingHandCursor)
        post_button.setStyleSheet("""
            QPushButton {
                background-color: #1DA1F2;
                color: white;
                border-radius: 15px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0D91E2;
            }
        """)
        post_button.clicked.connect(self.post_comment)
        button_layout.addWidget(post_button)

        input_layout.addLayout(button_layout)

        return input_widget

    def post_comment(self):
        comment_text = self.comment_edit.toPlainText().strip()
        if not comment_text:
            return

        user_session = UserSession()
        if not user_session.is_authenticated:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Authentication Required", "Please log in to post a comment.")
            return

        # Add comment to database
        #success = add_comment(
        #    self.post_id,
        #    user_session.user_id,
        #    user_session.profile_data.displayName,
        #    user_session.profile_data.profileImageUrl,
        #    comment_text
        #)

        #if success:
        #    self.comment_edit.clear()
        #

    def on_comment_added(self, comment_data):
        if comment_data.postId != self.post_id:
            return

        if self.post_data:
            self.post_data.commentsCount = (self.post_data.commentsCount or 0) + 1

        self.comments.append(comment_data)

        comment_widget = CommentWidget(comment_data)
        self.comments_layout.insertWidget(self.comments_layout.count() - 1, comment_widget)

        for i in range(self.centralWidget().layout().count()):
            widget = self.centralWidget().layout().itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.text().startswith("Comments ("):
                widget.setText(f"Comments ({len(self.comments)})")
                break

    def go_back(self):
        if self.parent_window and hasattr(self.parent_window, "stacked_widget"):
            self.parent_window.stacked_widget.setCurrentIndex(0)
            self.parent_window.stacked_widget.removeWidget(self)
        else:
            self.close()

    def closeEvent(self, event):
        if hasattr(self, 'listener'):
            if hasattr(self.listener, '_comments_watch') and self.listener._comments_watch:
                self.listener._comments_watch.unsubscribe()
        super().closeEvent(event)