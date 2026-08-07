import logging
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from google.cloud import firestore
from google.cloud.firestore_v1 import Query

from controller.comment_controller import CommentData
from controller.firebase_client import get_db
from controller.post_controller import delete_post, post_data_from_document
from modal.message import ConversationData, MessageData
from modal.post import PostData

logger = logging.getLogger(__name__)


class DeletePostTask(QRunnable):
    def __init__(self, post_id):
        super().__init__()
        self.post_id = post_id

    @Slot()
    def run(self):
        delete_post(self.post_id)


def delete_post_2(post_id):
    logger.debug("Post deletion signal received for %s", post_id)
    QThreadPool.globalInstance().start(DeletePostTask(post_id))


class FirestoreListener(QObject):
    newPostsSignal = Signal(PostData, bool)
    likeUpdatedSignal = Signal(str, int, bool)
    deleteSignal = Signal(str)
    initialPostsLoadedSignal = Signal(bool)
    removeFromStoreSignal = Signal(str)
    commentAddedSignal = Signal(CommentData)
    commentRemovedSignal = Signal(str)
    conversationUpdatedSignal = Signal(object)
    conversationRemovedSignal = Signal(str)
    messageUpdatedSignal = Signal(object)
    messageRemovedSignal = Signal(str)

    def __init__(self, post_limit=20, user_likes=None):
        super().__init__()
        self._post_watch = None
        self._post_document_watches = {}
        self._likes_watch = None
        self._comments_watch = None
        self._conversations_watch = None
        self._messages_watch = None
        self._initial_posts_loaded = False
        self._latest_post_timestamp = None
        self._time = datetime.now()
        self.post_limit = post_limit
        self.user_likes = user_likes or []

        self.deleteSignal.connect(delete_post_2)

    def set_user_likes(self, user_likes):
        self.user_likes = user_likes or []

    def subscribe_to_new_posts(self):
        self._initial_posts_loaded = False
        self._latest_post_timestamp = None

        def on_snapshot(snapshot, changes, read_time):
            for change in reversed(changes):
                if change.type.name in ["ADDED", "MODIFIED"]:
                    post_data = post_data_from_document(
                        change.document, user_likes=self.user_likes
                    )
                    timestamp = post_data.timestamp
                    is_genuinely_new = (
                            change.type.name == "ADDED"
                            and self._initial_posts_loaded
                            and isinstance(timestamp, datetime)
                            and (
                                    self._latest_post_timestamp is None
                                    or timestamp > self._latest_post_timestamp
                            )
                    )
                    if isinstance(timestamp, datetime) and (
                            self._latest_post_timestamp is None
                            or timestamp > self._latest_post_timestamp
                    ):
                        self._latest_post_timestamp = timestamp
                    self.newPostsSignal.emit(post_data, is_genuinely_new)

            if not self._initial_posts_loaded:
                self._initial_posts_loaded = True
                self.initialPostsLoadedSignal.emit(True)

        post_ref = get_db().collection("posts").order_by(
            field_path="timestamp", direction=Query.DESCENDING
        ).limit(self.post_limit)

        self._post_watch = post_ref.on_snapshot(on_snapshot)

    def subscribe_to_post_document(self, post_id):
        if not post_id or post_id in self._post_document_watches:
            return

        def on_snapshot(snapshots, changes, read_time):
            snapshot = snapshots[0] if isinstance(snapshots, (list, tuple)) else snapshots
            if snapshot is None or not snapshot.exists:
                self.removeFromStoreSignal.emit(post_id)
                return
            self.newPostsSignal.emit(
                post_data_from_document(snapshot, user_likes=self.user_likes),
                False,
            )

        post_ref = get_db().collection("posts").document(post_id)
        self._post_document_watches[post_id] = post_ref.on_snapshot(on_snapshot)

    def unsubscribe_from_post_document(self, post_id):
        watch = self._post_document_watches.pop(post_id, None)
        if watch:
            watch.unsubscribe()

    def subscribe_to_user_likes(self, user_id):
        def on_snapshot(snapshot, changes, read_time):
            for change in changes:
                if change.type.name in ["ADDED", "REMOVED"]:
                    doc = change.document
                    post_id = doc.get("postId")
                    post_ref = get_db().collection("posts").document(post_id)
                    post_doc = post_ref.get()
                    if post_doc.exists:
                        likes_count = post_doc.to_dict().get("likesCount", 0)
                        is_liked = change.type.name == "ADDED"
                        self.likeUpdatedSignal.emit(post_id, likes_count, is_liked)

        logger.debug("Subscribed to user like updates")
        likes_ref = get_db().collection_group("likes").where(
            filter=firestore.FieldFilter("userId", "==", user_id)
        )
        self._likes_watch = likes_ref.on_snapshot(on_snapshot)

    def subscribe_to_post_comments(self, post_id, limit=100):
        def on_snapshot(snapshot, changes, read_time):
            for change in changes:
                comment_id = change.document.id
                if change.type.name in ["ADDED", "MODIFIED"]:
                    comment_dict = change.document.to_dict()
                    comment_dict["id"] = comment_id
                    comment_dict["postId"] = post_id
                    self.commentAddedSignal.emit(CommentData.from_dict(comment_dict))
                elif change.type.name == "REMOVED":
                    self.commentRemovedSignal.emit(comment_id)

        comments_ref = get_db().collection("posts").document(post_id).collection(
            "comments"
        ).order_by(
            field_path="timestamp", direction=Query.ASCENDING
        ).limit(limit)
        self._comments_watch = comments_ref.on_snapshot(on_snapshot)

    def subscribe_to_conversations(self, user_id, limit=50):
        def on_snapshot(snapshot, changes, read_time):
            for change in changes:
                if change.type.name in ["ADDED", "MODIFIED"]:
                    self.conversationUpdatedSignal.emit(
                        ConversationData.from_document(change.document)
                    )
                elif change.type.name == "REMOVED":
                    self.conversationRemovedSignal.emit(change.document.id)

        conversations_ref = get_db().collection("conversations").where(
            filter=firestore.FieldFilter("memberIds", "array_contains", user_id)
        ).order_by(
            field_path="updatedAt", direction=Query.DESCENDING
        ).limit(limit)
        self._conversations_watch = conversations_ref.on_snapshot(on_snapshot)

    def subscribe_to_messages(self, conversation_id, limit=100):
        def on_snapshot(snapshot, changes, read_time):
            for change in changes:
                if change.type.name in ["ADDED", "MODIFIED"]:
                    self.messageUpdatedSignal.emit(
                        MessageData.from_document(change.document)
                    )
                elif change.type.name == "REMOVED":
                    self.messageRemovedSignal.emit(change.document.id)

        messages_ref = get_db().collection("conversations").document(
            conversation_id
        ).collection("messages").order_by(
            field_path="createdAt", direction=Query.ASCENDING
        ).limit_to_last(limit)
        self._messages_watch = messages_ref.on_snapshot(on_snapshot)

    def stop_listening(self):
        if self._post_watch:
            self._post_watch.unsubscribe()
            self._post_watch = None
        for watch in self._post_document_watches.values():
            watch.unsubscribe()
        self._post_document_watches.clear()
        if self._likes_watch:
            self._likes_watch.unsubscribe()
            self._likes_watch = None
        if self._comments_watch:
            self._comments_watch.unsubscribe()
            self._comments_watch = None
        if self._conversations_watch:
            self._conversations_watch.unsubscribe()
            self._conversations_watch = None
        if self._messages_watch:
            self._messages_watch.unsubscribe()
            self._messages_watch = None
