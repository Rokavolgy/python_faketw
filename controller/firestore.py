import json
from builtins import bool
from datetime import datetime

import requests
from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import QMessageBox
from google.cloud import firestore
from google.cloud.firestore_v1 import Query, SERVER_TIMESTAMP

from requests.exceptions import HTTPError
from google.oauth2.credentials import Credentials
from google.cloud.firestore import Client, Increment

from controller.user_session import UserSession
from modal import post
from modal.post import PostData
from modal.user import ProfileData

FIREBASE_REST_API = "https://identitytoolkit.googleapis.com/v1/accounts"

user_info_cache = {}
db = None


# Valami githubos kód fogalmam sincs honnan a register_user meg login_user meg ez is
def sign_in_with_email_and_password(api_key, email, password):
    request_url = "%s:signInWithPassword?key=%s" % (FIREBASE_REST_API, api_key)
    headers = {"content-type": "application/json; charset=UTF-8"}
    data = json.dumps({"email": email, "password": password, "returnSecureToken": True})

    req = requests.post(request_url, headers=headers, data=data)

    try:
        req.raise_for_status()
    except HTTPError as e:
        raise HTTPError(e, req.text)

    return req.json()


# Et voila!
# You are now connected to your firestore database and authenticated with the selected firebase user.
# All your firestore security rules now apply on this connection and it will behave like a normal client

def register_user(email, password):
    global db
    try:
        request_url = "%s:signUp?key=%s" % (FIREBASE_REST_API, "AIzaSyDkd5bMZ3frFvxNl39FayzWIfT3afNlJ4s")
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})

        req = requests.post(request_url, headers=headers, data=data)
        req.raise_for_status()
        response = req.json()

        user_session = UserSession()
        user_session.set_auth_data(
            user_id=response.get("localId"),
            id_token=response.get("idToken"),
            refresh_token=response.get("refreshToken"),
        )
        creds = Credentials(response["idToken"], response["refreshToken"])

        db = Client("mobilapp-7c1e5", creds)

        return True, response
    except Exception as e:
        print(f"Registration failed: {e}")
        return False, None


def login_user(email, password):
    global db
    try:
        response = sign_in_with_email_and_password(
            "AIzaSyDkd5bMZ3frFvxNl39FayzWIfT3afNlJ4s", email, password
        )
        user_session = UserSession()
        user_session.set_auth_data(
            user_id=response.get("localId"),
            id_token=response.get("idToken"),
            refresh_token=response.get("refreshToken"),
        )
        creds = Credentials(response["idToken"], response["refreshToken"])

        db = Client("mobilapp-7c1e5", creds)

        user_info = fetch_user_info(user_session.user_id)
        if user_info:
            profile_data = ProfileData.from_dict(user_info)
            user_session.set_profile_data(profile_data)
        else:
            QMessageBox.warning(None,"Warning","You haven't created a profile yet. Default values have been filled. ",QMessageBox.Ok)
            default_profile = ProfileData(
                id=user_session.user_id,
                displayName=email.split("@")[0],
                bio="",
                profileImageUrl="",
                coverImageUrl="",
                website="",
                location="",
                dateOfBirth=datetime(2000, 1, 1),
                createdAt=SERVER_TIMESTAMP,
                username=email.split("@")[0],
            )
            user_session.set_profile_data(default_profile)
            create_user_profile(user_session.user_id, default_profile)
        print(user_session.profile_data)
        return True, response
    except Exception as e:
        print(f"Login failed: {e}")
        return False, response


def fetch_posts():
    doc_ref = db.collection("posts").order_by(
        field_path="timestamp", direction=Query.DESCENDING
    )

    docs = doc_ref.stream()
    return docs


def fetch_user_posts(userId):
    doc_ref = db.collection("posts").where(
        filter=firestore.FieldFilter("userId", "==", userId)
    ).order_by(
        field_path="timestamp", direction=Query.DESCENDING
    )
    docs = doc_ref.stream()
    return docs


def fetch_user_info(userId):
    if userId in user_info_cache:
        print("Cache hit for userId:", userId)
        return user_info_cache[userId]
    doc_ref = db.collection("userdata").document(userId)
    doc = doc_ref.get()
    if doc.exists:
        user_data = doc.to_dict()
        user_info_cache[userId] = user_data
        return user_data
    else:
        return None


def clear_cache():
    global user_info_cache
    user_info_cache = {}
    print("User info cleared.")


def fetch_user_likes(userId):
    try:
        doc_ref = db.collection_group("likes").where(
            filter=firestore.FieldFilter("userId", "==", userId)
        )
        docs = doc_ref.stream()
        liked_posts = [doc.get("postId") for doc in docs]  # postId userId timeStamp
        print(liked_posts)
        return liked_posts
    except Exception as e:
        print(f"Error fetching user likes: {e}")
        return []


def fetch_posts_and_user_info(userId=None):
    if userId:
        posts = fetch_user_posts(userId)
    else:
        posts = fetch_posts()
    posts_with_user_info = []
    user_session = UserSession()
    user_likes = fetch_user_likes(user_session.user_id)
    user_session.set_user_likes(user_likes)
    for post_doc in posts:
        post_dict = post_doc.to_dict()
        post_data = post.PostData.from_dict(post_dict)
        userId = post_data.userId

        user_data = fetch_user_info(userId)

        if user_data:
            user = ProfileData.from_dict(user_data)
            post_data.userName = user.displayName
            post_data.userProfilePicUrl = user.profileImageUrl
            post_data.userData = user
            if post_data.id in user_likes:
                post_data.likedByCurrentUser = True
            posts_with_user_info.append(post_data)

    return posts_with_user_info


def fetch_post_by_id(post_id):
    """
    Fetch a specific post by its ID and enrich it with user data

    Args:
        post_id (str): The ID of the post to fetch

    Returns:
        PostData: The post data object with user info, or None if not found
    """
    try:
        post_ref = db.collection("posts").document(post_id)
        post_doc = post_ref.get()

        if not post_doc.exists:
            print(f"Post {post_id} not found")
            return None

        post_dict = post_doc.to_dict()
        post_dict["id"] = post_id

        post_data = post.PostData.from_dict(post_dict)

        user_id = post_data.userId
        user_data = fetch_user_info(user_id)

        if user_data:
            user = ProfileData.from_dict(user_data)
            post_data.userName = user.displayName
            post_data.userProfilePicUrl = user.profileImageUrl
            post_data.userData = user

            user_session = UserSession()
            if user_session.is_authenticated:
                user_likes = user_session.user_likes
                if post_id in user_likes:
                    post_data.likedByCurrentUser = True

        return post_data

    except Exception as e:
        print(f"Error fetching post: {e}")
        return None


def create_new_post(post_data):
    try:
        post_dict = post_data.to_dict(post_data)  # ???

        db.collection("posts").add(post_dict, post_dict["id"])
        return True
    except Exception as e:
        print(f"Error creating post: {e}")
        return False


def delete_post(post_id):
    try:
        post_ref = db.collection("posts").document(post_id)
        post_ref.delete()
        return True
    except Exception as e:
        print(f"Error deleting post: {e}")
        return False


def like_post(post_id, user_id):
    try:
        user_session = UserSession()
        post_ref = db.collection("posts").document(post_id)
        post_doc = post_ref.get()

        if not post_doc.exists:
            print(f"Post {post_id} not found")
            return False

        like_doc_ref = post_ref.collection("likes").document(user_id)
        if like_doc_ref.get().exists:
            print(f"User {user_id} already liked post {post_id}")
            return False

        like_data = {"userId": user_id, "postId": post_id, "timestamp": datetime.now()}
        like_doc_ref.set(like_data)
        user_session.add_user_like(post_id)

        post_ref.update({"likesCount": Increment(1)})
        return True
    except Exception as e:
        print(f"Error liking post: {e}")
        return False


def unlike_post(post_id, user_id):
    try:
        user_session = UserSession()
        post_ref = db.collection("posts").document(post_id)
        post_doc = post_ref.get()

        if not post_doc.exists:
            print(f"Post {post_id} not found")
            return False

        # Check if like exists
        like_doc_ref = post_ref.collection("likes").document(user_id)
        user_session.remove_user_like(post_id)
        if not like_doc_ref.get().exists:
            print(f"User {user_id} hasn't liked post {post_id}")
            return False

        # Delete the like document
        like_doc_ref.delete()

        post_ref.update({"likesCount": Increment(-1)})
        return True
    except Exception as e:
        print(f"Error unliking post: {e}")
        return False


def toggle_post_like(post_id):
    """
    Toggle the current user's like status for a post.
    """
    user_session = UserSession()
    if not user_session.is_authenticated:
        print("User not authenticated")
        return False

    user_id = user_session.user_id

    try:
        post_ref = db.collection("posts").document(post_id)
        like_doc_ref = post_ref.collection("likes").document(user_id)

        if like_doc_ref.get().exists:
            print("a")
            return unlike_post(post_id, user_id)
        else:
            print("b")
            return like_post(post_id, user_id)
    except Exception as e:
        print(f"Error toggling post like: {e}")
        return False


def update_user_profile(user_id, profile_data):
    try:
        user_ref = db.collection("userdata").document(user_id)
        print("siker")
        print(profile_data.to_dict(profile_data))
        user_ref.set(profile_data.to_dict_without_id(profile_data), merge=True)
        return True
    except Exception as e:
        print(f"Error updating user profile: {e}")
        return False


def create_user_profile(user_id, profile_data):
    try:
        user_ref = db.collection("userdata").document(user_id)
        user_ref.set(profile_data.to_dict_without_id(profile_data), merge=True)
        return True
    except Exception as e:
        print(f"Error creating user profile: {e}")
        return False


class FirestoreListener(QObject):
    newPostsSignal = pyqtSignal(PostData)
    likeUpdatedSignal = pyqtSignal(str, int, bool)
    deleteSignal = pyqtSignal(str)
    removeFromStoreSignal = pyqtSignal(str)


    def __init__(self):
        super().__init__()
        self._post_watch = None
        self._likes_watch = None
        self.deleteSignal.connect(self.delete_post_2)

    def subscribe_to_new_posts(self):
        def on_snapshot(snapshot, changes, read_time):
            post_data = None
            for change in changes:
                if change.type.name in ["ADDED", "MODIFIED"]:
                    post_dict = change.document.to_dict()
                    post_dict["id"] = change.document.id
                    post_data = post.PostData.from_dict(post_dict)
                    user_id = post_data.userId
                    user_data = fetch_user_info(user_id)
                    if user_data:
                        user = ProfileData.from_dict(user_data)
                        post_data.userName = user.displayName
                        post_data.userProfilePicUrl = user.profileImageUrl
                        post_data.userData = user
                    else:
                        print(f"User data not found for userId: {user_id}")


                if change.type.name == "REMOVED":
                    post_id = change.document.id
                    self.removeFromStoreSignal.emit(post_id)
                if post_data is not None:
                    self.newPostsSignal.emit(post_data)

        post_ref = db.collection("posts").order_by(
            field_path="timestamp", direction=Query.DESCENDING
        ).limit(80)

        self._post_watch = post_ref.on_snapshot(on_snapshot)
        # teljesen felesleges
    def subscribe_to_user_likes(self, user_id):
        def on_snapshot(snapshot, changes, read_time):
            for change in changes:
                if change.type.name in ["ADDED", "REMOVED"]:
                    doc = change.document
                    post_id = doc.get("postId")
                    post_ref = db.collection("posts").document(post_id)
                    post_doc = post_ref.get()
                    if post_doc.exists:
                        likes_count = post_doc.to_dict().get("likesCount", 0)
                        is_liked = change.type.name == "ADDED"
                        self.likeUpdatedSignal.emit(post_id, likes_count, is_liked)

        print("Felesleges funkcióra feliratkozva.")
        likes_ref = db.collection_group("likes").where(
            filter=firestore.FieldFilter("userId", "==", user_id)
        )
        self._likes_watch = likes_ref.on_snapshot(on_snapshot)

    def delete_post_2(self, post_id):
        print("signal received")
        delete_post(post_id)

    def stop_listening(self):
        if self._post_watch:
            self._post_watch.unsubscribe()
        if self._likes_watch:
            self._likes_watch.unsubscribe()


# Use google.oauth2.credentials and the response object to create the correct user credentials
