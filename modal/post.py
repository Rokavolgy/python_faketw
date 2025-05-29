from dataclasses import dataclass
from datetime import datetime, timezone
from time import gmtime
from typing import List, Optional

import google.cloud.firestore_v1
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from nbclient.client import timestamp

from modal.user import ProfileData
from controller.user_session import UserSession

@dataclass
class PostData:
    content: str
    commentsCount: int
    userProfilePicUrl: str
    mediaUrls: List[str]
    userName: str
    id: str
    userId: str
    likedByCurrentUser: bool
    likesCount: int
    timestamp: datetime
    userData: Optional["ProfileData"] = None

    @classmethod
    def from_dict(cls, data):
        user_session = UserSession()
        a = data.get('timestamp',"")
        return cls(
            content=data.get("content", ""),
            commentsCount=data.get("commentsCount", 0),
            userProfilePicUrl=data.get("userProfilePicUrl", ""),
            mediaUrls=data.get("mediaUrls", []),
            userName=data.get("userName", "Unknown User"),
            id=data.get("id", ""),
            userId=data.get("userId", ""),
            likedByCurrentUser=user_session.check_if_user_liked(data.get("id", "")),
            likesCount=data.get("likesCount", 0),
            timestamp=a.astimezone(tz=None),
            userData=data.get("userData", None),
        )

    @classmethod
    def to_dict(cls, post):
        return {
            "content": post.content,
            "commentsCount": post.commentsCount,
            "userProfilePicUrl": post.userProfilePicUrl,
            "mediaUrls": post.mediaUrls,
            "userName": post.userName,
            "id": post.id,
            "userId": post.userId,
            "likedByCurrentUser": post.likedByCurrentUser,
            "likesCount": post.likesCount,
            "timestamp": SERVER_TIMESTAMP,
        }
