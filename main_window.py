import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from comment_view import CommentView
from login_window import LoginWindow
from post_widget import PostsWindow
from profile_view import ProfileView
from signup_window import SignupWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.posts_view = None
        self.setWindowTitle("Fwitter")
        self.setMinimumSize(600, 800)
        self.setMaximumWidth(1000)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        font_id = QFontDatabase.addApplicationFont("res/fonts/WixMadeforText-Regular.ttf")
        font_id = QFontDatabase.addApplicationFont("res/fonts/WixMadeforText-Bold.ttf")

        if font_id != -1:
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            print(f"Font loaded successfully! Available families: {font_families}")
        else:
            print("Failed to load font.")
        self.show_login_window()

    def show_login_window(self):
        if hasattr(self, 'signup_window'):
            self.signup_window.close()
        self.login_window = LoginWindow()
        self.login_window.loginSuccessful.connect(self.on_login_successful)
        self.login_window.signupRequested.connect(self.show_signup_window)
        self.login_window.show()

    def show_signup_window(self):

        if hasattr(self, 'login_window'):
            self.login_window.close()
        self.signup_window = SignupWindow()
        self.signup_window.registrationCompleted.connect(self.on_registration_completed)

        self.signup_window.loginRequested.connect(self.show_login_window)
        self.signup_window.show()

    def on_registration_completed(self, profile_data):
        self.init_views()
        self.show()

    def on_login_successful(self):

        self.init_views()
        self.show()

    def init_views(self):

        self.posts_view = PostsWindow()
        self.posts_view.profileSwitchRequested.connect(self.show_profile_view)
        self.posts_view.commentSwitchRequested.connect(self.show_comment_view)
        self.stacked_widget.addWidget(self.posts_view)

        self.stacked_widget.setCurrentIndex(0)

    def show_profile_view(self, userId):

        profile_view = ProfileView(user_id=userId, parent_window=self)

        self.stacked_widget.addWidget(profile_view)
        self.stacked_widget.setCurrentIndex(self.stacked_widget.count() - 1)

    def show_comment_view(self, post_id):

        comment_window = CommentView(post_id=post_id, parent_window=self)
        self.stacked_widget.addWidget(comment_window)
        self.stacked_widget.setCurrentIndex(self.stacked_widget.count() - 1)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()

    # window.show()
    sys.exit(app.exec_())
