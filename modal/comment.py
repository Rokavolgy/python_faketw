from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CommentData:
    id: str
    postId: str
    userId: str
    userName: str
    userProfilePicUrl: str
    content: str
    timestamp: datetime

    @classmethod
    def from_dict(cls, data):
        timestamp = data.get("timestamp")
        if timestamp and hasattr(timestamp, "astimezone"):
            timestamp = timestamp.astimezone(tz=None)

        return cls(
            id=data.get("id", ""),
            postId=data.get("postId", ""),
            userId=data.get("userId", ""),
            userName=data.get("userName", "Unknown User"),
            userProfilePicUrl=data.get("userProfilePicUrl", ""),
            content=data.get("content", ""),
            timestamp=timestamp,
        )

    @classmethod
    def to_dict(cls, comment):
        return {
            "id": comment.id,
            "postId": comment.postId,
            "userId": comment.userId,
            "userName": comment.userName,
            "userProfilePicUrl": comment.userProfilePicUrl,
            "content": comment.content,
            "timestamp": comment.timestamp,
        }
