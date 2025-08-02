import os
from typing import List
from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QSizePolicy,
)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Signal, Qt, QThreadPool
from datetime import datetime

from windows_toasts import WindowsToaster, Toast, ToastDisplayImage

from controller.image_loader_task import ImageLoaderTask
from controller.firestore import toggle_post_like, FirestoreListener
from controller.user_session import UserSession
from create_post_widget import CreatePostWidget
from custom_widget.like_comment_button import PostButton
from modal.constants import Constants
from modal.post import PostData


class ClickableLabel(QLabel):
    clicked = Signal(str)

    def __init__(self, userId=None):
        super().__init__()
        self.userId = userId

    def mousePressEvent(self, event):
        if self.userId:
            self.clicked.emit(self.userId)
        else:
            self.clicked.emit("")
        super().mousePressEvent(event)


class PostsWindow(QMainWindow):
    profileSwitchRequested = Signal(str)
    commentSwitchRequested = Signal(str)

    def __init__(self, posts_data: List[PostData]):
        super().__init__()

        self.posts_layout = None
        self.posts_data = posts_data
        self.toaster = WindowsToaster("Fwitter")
        self.thread_pool = QThreadPool()
        self.listener = FirestoreListener()
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.likeUpdatedSignal.connect(self.on_post_like)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)
        self.init_ui()



        self.listener.subscribe_to_new_posts()




    def init_ui(self):
        self.setWindowTitle("Posts Viewer")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setMaximumWidth(1000)
        scroll.setAlignment(
            Qt.AlignHCenter
        )  # miert nincs kozepen ez a vacak ??????????????????????

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.posts_layout = QVBoxLayout(container)


        for post in self.posts_data:
            post_widget = PostWidget(post)
            post_widget.profileClicked.connect(self.switch_to_profile_mode)
            post_widget.commentClicked.connect(self.switch_to_comment_mode)
            post_widget.deleteClicked.connect(self.listener.delete_post_2)
            self.posts_layout.addWidget(post_widget, stretch=1)

        self.posts_layout.addStretch()

        scroll.setWidget(container)

        main_layout.addWidget(scroll, 1)

        self.create_post_widget = CreatePostWidget(
            user_id="current_user_id", user_name="Your Username"
        )
        self.create_post_widget.postCreated.connect(self.on_post_created)

        self.create_post_widget.setMaximumHeight(200)

        main_layout.addWidget(self.create_post_widget)

        self.setCentralWidget(main_widget)

    def add_post_widget(self, post: PostData):
        post_widget = PostWidget(post)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        self.posts_layout.addWidget(post_widget, stretch=1)

    def switch_to_profile_mode(self, userId):
        print(f"profile show: {userId}")
        self.profileSwitchRequested.emit(userId)

    def switch_to_comment_mode(self, postId):
        print(f"comment show: {postId}")
        self.commentSwitchRequested.emit(postId)

    def on_post_created(self, new_post: PostData):
        self.add_post_widget(new_post)

        self.posts_data.insert(0, new_post)


    def on_post_notification(self, post_data: PostData):
        # keresés hogy van-e

        self.toast = Toast()
        self.toast.text_fields = ['New Post', 'Hello, World!']
        for i, post in enumerate(self.posts_data):
            if post.id == post_data.id:
                print("Poszt már létezik. Adatmódosítás.")
                self.posts_data[i] = post_data

                # Adat frissítés
                post_widget = self.posts_layout.itemAt(i).widget()
                post_widget.post_data = post_data
                post_widget.update()

                print(post_data)
                return
        self.posts_data.insert(0, post_data)

        if not UserSession().user_id == post_data.userId:
            print("értesítés kapva: új poszt")
            self.toast.text_fields =["New Post", "New post from " + post_data.userName]
            self.toaster.show_toast(self.toast)
        # új widget mint an onpostcreated ben
        post_widget = PostWidget(post_data)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        self.posts_layout.insertWidget(0, post_widget)

    def on_post_like(self):
        #updates elsewhere
        print("ok")
        pass

    def on_remove_from_store(self, post_id):
        print("értesítés kapva a következőről: törölni kell a posztot")
        for i, post in enumerate(self.posts_data):
            if post.id == post_id:
                print("Poszt törölve.")
                del self.posts_data[i]

                post_widget = self.posts_layout.itemAt(i).widget()
                self.posts_layout.removeWidget(post_widget)
                post_widget.deleteLater()
                break


class PostWidget(QWidget):
    profileClicked = Signal(str)  # PostWindow
    likeClicked = Signal(str)  # FirestoreListener
    commentClicked = Signal(str)  # Nothing
    deleteClicked = Signal(str)  # FirestoreListener

    def __init__(self, post_data: PostData, hide_buttons=False):
        super().__init__()
        self.post_data = post_data
        self.thread_pool = QThreadPool()
        self.setMinimumWidth(400)
        self.setMaximumWidth(1000)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred))
        self.profile_pic = None
        self.user_info = None
        self.username = None
        self.post_content = None
        self.post_stats = None
        self.post_image = None
        self.hide_buttons = hide_buttons
        self.init_ui()

    def update_image(self, label, pixmap, height=400, width=300):
        if label is None:
            print("Warning: label not found")

        scaled_pixmap = pixmap.scaled(
            height, width, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        label.setPixmap(scaled_pixmap)

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        header_layout = QHBoxLayout()

        self.profile_pic = ClickableLabel(self.post_data.userId)
        self.profile_pic.setFixedSize(40, 40)
        self.profile_pic.setStyleSheet(
            "background-color: lightgray; border-radius: 20px;"
        )
        self.profile_pic.clicked.connect(self.on_profile_clicked)

        if self.post_data.userProfilePicUrl:
            image_url = Constants.STORAGE_URL + self.post_data.userProfilePicUrl
            task = ImageLoaderTask(
                image_url,
                lambda pixmap: self.update_image(self.profile_pic, pixmap, 40, 40),
            )
            self.thread_pool.start(task)

        header_layout.addWidget(self.profile_pic)

        user_info_layout = QVBoxLayout()

        self.username_label = QLabel(self.post_data.userName)
        self.username_label.setFont(QFont("Wix Madefor Text", 12, QFont.Bold))

        timestamp = self.post_data.timestamp
        time_str = "Unknown date"
        if timestamp and hasattr(timestamp, "year"):
            time_str = datetime.strftime(timestamp, "%Y-%m-%d %H:%M")
        else:
            print("Érvénytelen dátum")
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet("color: gray;")

        user_info_layout.addWidget(self.username_label)
        user_info_layout.addWidget(self.time_label)
        header_layout.addLayout(user_info_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # szöveg
        self.content_label = QLabel(self.post_data.content)
        self.content_label.setFont(QFont("Wix Madefor Text", 12))
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("margin: 10px 0;")
        main_layout.addWidget(self.content_label)

        # kép
        if self.post_data.mediaUrls:
            self.image_label = QLabel()
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("margin: 10px 0;")

            # Load the image asynchronously
            image_url = Constants.STORAGE_URL + self.post_data.mediaUrls[0]
            task = ImageLoaderTask(
                image_url, lambda pixmap: self.update_image(self.image_label, pixmap)
            )
            self.thread_pool.start(task)

            main_layout.addWidget(self.image_label)

        # kommentelés meg kedvelés
        stats_layout = QHBoxLayout()
        stats_layout.setAlignment(Qt.AlignCenter)
        heart_filled_icon = (
            "icons/heart_filled.png"
            if self.post_data.likedByCurrentUser
            else "icons/heart.png"
        )

        self.like_button = PostButton(
            heart_filled_icon,
            f" {self.post_data.likesCount}" if self.post_data.likesCount else " Like",
        )
        self.like_button.clicked.connect(
            lambda: self.on_like_clicked(self.post_data.id)
        )
        self.like_button.setFixedHeight(50)

        self.comment_button = PostButton(
            "icons/comment.png",
            (
                f" {self.post_data.commentsCount}"
                if self.post_data.commentsCount
                else " Comment"
            ),
        )
        self.comment_button.clicked.connect(
            lambda: self.on_comment_clicked(self.post_data.id)
        )
        self.comment_button.setFixedHeight(50)

        self.delete_button = PostButton("icons/delete.png", "Delete")
        self.delete_button.clicked.connect(
            lambda: self.on_delete_clicked(self.post_data.id)
        )
        self.delete_button.setFixedHeight(50)

        if not self.hide_buttons:
            stats_layout.addWidget(self.like_button)
            stats_layout.addWidget(self.comment_button)
            stats_layout.addStretch()
            user_session = UserSession()
            if user_session.user_id == self.post_data.userId:
                stats_layout.addWidget(self.delete_button)
            main_layout.addLayout(stats_layout)

        self.separator = QLabel()
        self.separator.setFixedHeight(1)
        self.separator.setStyleSheet("background-color: lightgray;")
        main_layout.addWidget(self.separator)

        self.post_data_old = self.post_data

    def on_profile_clicked(self, userId):
        self.profileClicked.emit(userId)

    def on_like_clicked(self, post_id):

        self.likeClicked.emit(post_id)  # main szálon fut úgyhogy szaggat, de legalább eltakarja a nyomi animációt
        toggle_post_like(post_id)

    def on_comment_clicked(self, post_id):

        self.commentClicked.emit(post_id)
        print("Képzeletben működik a kommentelés")
        # nem csinal semmit

    def on_delete_clicked(self, post_id):
        self.deleteClicked.emit(post_id)

    def update(self):
        self.update_ui()

    def update_ui(self):
        self.content_label.setText(self.post_data.content)

        self.username_label.setText(self.post_data.userName)

        icon_path = (
            "icons/heart_filled.png"
            if self.post_data.likedByCurrentUser
            else "icons/heart.png"
        )
        self.like_button.setIcon(QIcon(icon_path))
        self.like_button.setText(
            f" {self.post_data.likesCount}" if self.post_data.likesCount else " Like"
        )

        self.comment_button.setText(
            f" {self.post_data.commentsCount}"
            if self.post_data.commentsCount
            else " Comment"
        )

        if (
                hasattr(self, "post_data_old")
                and self.post_data_old.userProfilePicUrl != self.post_data.userProfilePicUrl
        ):
            if self.post_data.userProfilePicUrl:
                image_url = Constants.STORAGE_URL + self.post_data.userProfilePicUrl
                task = ImageLoaderTask(
                    image_url,
                    lambda pixmap: self.update_image(self.profile_pic, pixmap, 40, 40),
                )
                self.thread_pool.start(task)
