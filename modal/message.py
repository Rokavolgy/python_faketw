from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ConversationData:
    id: str
    memberIds: list[str]
    updatedAt: datetime | None
    lastMessagePreview: str = ""
    lastMessageType: str = ""
    lastSenderId: str = ""
    lastMessageAt: datetime | None = None

    @classmethod
    def from_document(cls, document):
        data = document.to_dict()
        return cls(
            id=document.id,
            memberIds=data.get("memberIds", []),
            updatedAt=data.get("updatedAt"),
            lastMessagePreview=data.get("lastMessagePreview", ""),
            lastMessageType=data.get("lastMessageType", ""),
            lastSenderId=data.get("lastSenderId", ""),
            lastMessageAt=data.get("lastMessageAt"),
        )

    def other_user_id(self, current_user_id: str) -> str:
        return next((uid for uid in self.memberIds if uid != current_user_id), "")


@dataclass(slots=True)
class MessageData:
    id: str
    senderId: str
    type: str
    text: str
    createdAt: datetime | None
    storageBucket: str = ""
    storagePath: str = ""

    @classmethod
    def from_document(cls, document):
        data = document.to_dict()
        return cls(
            id=document.id,
            senderId=data.get("senderId", ""),
            type=data.get("type", "text"),
            text=data.get("text", ""),
            createdAt=data.get("createdAt"),
            storageBucket=data.get("storageBucket", ""),
            storagePath=data.get("storagePath", ""),
        )
