import platform
from datetime import datetime

from PySide6.QtCore import Signal, QThreadPool, Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QScrollArea, QSizePolicy, QLabel

if platform.system() == "Windows":
    from windows_toasts import WindowsToaster, Toast, ToastDisplayImage
else:
    WindowsToaster = None
    Toast = None
    ToastDisplayImage = None

from controller.firestore import FirestoreListener
from controller.icon_cache import IconCache
from controller.user_session import UserSession
from modal.constants import Constants
from modal.post import PostData
from widgets.create_post_widget import CreatePostWidget
from widgets.post_widget import PostWidget


class PostsWindow(QMainWindow):
    profileSwitchRequested = Signal(str)
    commentSwitchRequested = Signal(str)
    initialFetchComplete = Signal(bool)

    def __init__(self):
        super().__init__()
        # time log
        # print("PostsWindow init started")
        self.time = datetime.now()
        self.loading_label = None
        self.initial_load_count = 0
        self.posts_layout = None
        self.scroll = None
        self.initial_fetch_done = False
        self.posts_data = []
        if platform.system() == "Windows":
            self.toaster = WindowsToaster("Fwitter")
        else:
            self.toaster = None
        self.thread_pool = QThreadPool()
        self.listener = FirestoreListener()
        self.listener.newPostsSignal.connect(self.on_post_notification)
        self.listener.likeUpdatedSignal.connect(self.on_post_like)
        self.listener.removeFromStoreSignal.connect(self.on_remove_from_store)
        self.listener.initialPostsLoadedSignal.connect(self.on_initial_fetch_complete)
        self.init_ui()
        # print("PostsWindow init done time: " + str(datetime.now() - self.time))

        self.listener.subscribe_to_new_posts()
        # print("PostsWindow subscribed to new posts" + str(datetime.now() - self.time))
        self.preload_while_fetching()
        # print("PostsWindow preload done time: " + str(datetime.now() - self.time))

    def init_ui(self):
        self.setWindowTitle("Posts Viewer")
        self.setMinimumSize(600, 800)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setMaximumWidth(1000)
        self.scroll.setAlignment(
            Qt.AlignHCenter
        )  # ysd

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.posts_layout = QVBoxLayout(container)

        self.posts_layout.addStretch()

        self.scroll.setWidget(container)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll, 1)

        self.create_post_widget = CreatePostWidget(
            user_id="current_user_id", user_name="Your Username"
        )
        self.create_post_widget.postCreated.connect(self.on_post_created)

        self.create_post_widget.setMaximumHeight(200)

        main_layout.addWidget(self.create_post_widget)

        self.setCentralWidget(main_widget)

        self.loading_label = QLabel("Refreshing posts...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.posts_layout.addWidget(self.loading_label)

    def preload_while_fetching(self):
        IconCache.get_icon("res/icons/heart.png")
        IconCache.get_icon("res/icons/heart_filled.png")
        IconCache.get_icon("res/icons/comment.png")
        IconCache.get_icon("res/icons/delete.png")

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
        # search

        self.toast = Toast()
        self.toast.text_fields = ['New Post', 'Hello, World!']
        if self.initial_fetch_done:
            for i, post in enumerate(self.posts_data):
                if post.id == post_data.id:
                    print("Poszt már létezik. Adatmódosítás.")
                    self.posts_data[i] = post_data

                    # Adat frissítés
                    post_widget = self.posts_layout.itemAt(i).widget()
                    post_widget.post_data = post_data
                    post_widget.refresh_ui()  # renamed from update()

                    print(post_data)
                    return
        self.posts_data.insert(0, post_data)

        if self.initial_fetch_done and not UserSession().user_id == post_data.userId:
            print("értesítés kapva: új poszt")
            self.toast.text_fields = ["New Post", "New post from " + post_data.userName]
            if self.toaster:
                if post_data.mediaUrls:
                    image_url = Constants.STORAGE_URL + post_data.mediaUrls[0]
                    self.toast.display_image = ToastDisplayImage(image_url)
                else:
                    self.toast.display_image = None
                self.toaster.show_toast(self.toast)
        # új widget mint an onpostcreated ben
        # print("Widget create time: " + str(datetime.now() - self.time))

        post_widget = PostWidget(post_data)
        post_widget.profileClicked.connect(self.switch_to_profile_mode)
        post_widget.commentClicked.connect(self.switch_to_comment_mode)
        post_widget.deleteClicked.connect(self.listener.delete_post_2)
        if self.initial_fetch_done:
            self.posts_layout.insertWidget(0, post_widget)
        else:
            self.posts_layout.addWidget(post_widget)

    def on_post_like(self):
        # updates elsewhere
        print("ok")
        pass

    def on_remove_from_store(self, post_id):
        for i, post in enumerate(self.posts_data):
            if post.id == post_id:
                print("Poszt törölve.")
                del self.posts_data[i]

                post_widget = self.posts_layout.itemAt(i).widget()
                self.posts_layout.removeWidget(post_widget)
                post_widget.deleteLater()
                break

    def on_initial_fetch_complete(self):
        self.initial_fetch_done = True
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.listener.initialPostsLoadedSignal.disconnect()
        # print("Initial fetch complete, removing loading label time: " + str(datetime.now() - self.time))
        self.loading_label.deleteLater()
