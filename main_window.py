# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --python-flag=no_docstrings
# nuitka-project: --python-flag=no_site
# nuitka-project: --python-flag=no_asserts
# nuitka-project: --python-flag=no_warnings
# nuitka-project: --remove-output
# nuitka-project: --nofollow-import-to=PIL.ImageEnhance
# nuitka-project: --nofollow-import-to=PIL.ImageMorph
# nuitka-project: --nofollow-import-to=PIL.PdfImagePlugin
# nuitka-project: --nofollow-import-to=PIL.PalmImagePlugin
# nuitka-project: --nofollow-import-to=PIL.ImageFilter
# nuitka-project: --nofollow-import-to=PIL.ImageTk
# nuitka-project: --nofollow-import-to=PIL.ImageWin
# nuitka-project: --nofollow-import-to=PIL.BufrStubImagePlugin
# nuitka-project: --nofollow-import-to=PIL.GribStubImagePlugin
# nuitka-project: --nofollow-import-to=PIL.MpegImagePlugin
# nuitka-project: --nofollow-import-to=PIL.Hdf5StubImagePlugin
# nuitka-project: --nofollow-import-to=PIL.PsdImagePlugin
# nuitka-project: --noinclude-qt-plugins=tls
# nuitka-project: --noinclude-qt-plugins=iconengines
# nuitka-project: --noinclude-qt-plugins=printsupport
# nuitka-project: --nofollow-import-to=PySide6.QtNetwork
# nuitka-project  --nofollow-import-to=webbrowser
# nuitka-project: --nofollow-import-to=tarfile
# nuitka-project: --nofollow-import-to=tomllib
# nuitka-project: --nofollow-import-to=bz2
# nuitka-project: --nofollow-import-to=unittest
# nuitka-project: --nofollow-import-to=PIL.ImageCms
# nuitka-project: --nofollow-import-to=_imagingtk



import logging
import sys

from PySide6.QtCore import Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from controller.logging_config import configure_logging
from modal.user import ProfileData

logger = logging.getLogger(__name__)
configure_logging()

from views.login_window import LoginWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.posts_view = None
        self.setWindowTitle("Fwitter")
        self.setMinimumSize(600, 800)
        self.setMaximumWidth(1200)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        font_id = QFontDatabase.addApplicationFont("res/fonts/WixMadeforText-Regular.ttf")
        font_id = QFontDatabase.addApplicationFont("res/fonts/WixMadeforText-Bold.ttf")

        if font_id != -1:
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            logger.debug("Application font loaded: %s", font_families)
        else:
            logger.warning("Could not load the application font")
        self.show_login_window()

    @Slot()
    def show_login_window(self):
        if hasattr(self, 'signup_window'):
            self.signup_window.close()
        self.login_window = LoginWindow()
        self.login_window.loginSuccessful.connect(self.on_login_successful)
        self.login_window.signupRequested.connect(self.show_signup_window)
        self.login_window.show()

    @Slot()
    def show_signup_window(self):

        if hasattr(self, 'login_window'):
            self.login_window.close()
        from views.signup_window import SignupWindow

        self.signup_window = SignupWindow()
        self.signup_window.registrationCompleted.connect(self.on_registration_completed)

        self.signup_window.loginRequested.connect(self.show_login_window)
        self.signup_window.show()

    @Slot(ProfileData)
    def on_registration_completed(self, profile_data):
        self.init_views()
        self.show()

    @Slot()
    def on_login_successful(self):

        self.init_views()
        self.show()

    def init_views(self):
        from views.posts_window import PostsWindow

        self.posts_view = PostsWindow()
        self.posts_view.profileSwitchRequested.connect(self.show_profile_view)
        self.posts_view.commentSwitchRequested.connect(self.show_comment_view)
        self.posts_view.messagesRequested.connect(self.show_messages_view)
        self.stacked_widget.addWidget(self.posts_view)

        self.stacked_widget.setCurrentIndex(0)

    @Slot(str)
    def show_profile_view(self, userId):
        from views.profile_view import ProfileView

        profile_view = ProfileView(user_id=userId, parent_window=self)

        self.stacked_widget.addWidget(profile_view)
        self.stacked_widget.setCurrentIndex(self.stacked_widget.count() - 1)

    @Slot(str)
    def show_comment_view(self, post_id):
        from views.comment_view import CommentView

        comment_window = CommentView(post_id=post_id, parent_window=self)
        comment_window.profileRequested.connect(self.show_profile_view)
        self.stacked_widget.addWidget(comment_window)
        self.stacked_widget.setCurrentIndex(self.stacked_widget.count() - 1)

    @Slot()
    def show_messages_view(self, replace_current=None):
        from views.messages_window import MessagesWindow

        previous = replace_current or self.stacked_widget.currentWidget()
        messages_view = MessagesWindow(parent_window=self)
        messages_view.chatRequested.connect(self.show_chat_view)
        self.stacked_widget.addWidget(messages_view)
        self.stacked_widget.setCurrentWidget(messages_view)
        if previous and previous is not self.posts_view and previous is not messages_view:
            if hasattr(previous, "cleanup"):
                previous.cleanup()
            self.stacked_widget.removeWidget(previous)
            previous.deleteLater()

    @Slot(str)
    def show_chat_view(self, other_user_id):
        from views.chat_view import ChatView

        previous = self.stacked_widget.currentWidget()
        try:
            chat_view = ChatView(other_user_id, parent_window=self)
        except Exception:
            logger.exception("Unable to open conversation")
            return
        self.stacked_widget.addWidget(chat_view)
        self.stacked_widget.setCurrentWidget(chat_view)
        if previous and previous is not self.posts_view:
            if hasattr(previous, "cleanup"):
                previous.cleanup()
            self.stacked_widget.removeWidget(previous)
            previous.deleteLater()


if __name__ == "__main__":
    # checking for nuitka builds
    if "--check-avif" in sys.argv:
        from widgets.avif_widget import avif_codec_self_test

        if avif_codec_self_test():
            print("AVIF codec check passed")
            sys.exit(0)
        print("AVIF codec check failed", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())
