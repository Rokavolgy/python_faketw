from dataclasses import dataclass
from datetime import datetime

UPLOAD_URL = "https://lhojsvnzsgqzalyzmkne.supabase.co/functions/v1/storage-upload"
STORAGE_URL = (
    "https://lhojsvnzsgqzalyzmkne.supabase.co/storage/v1/object/public/faktw2/"
)


@dataclass
class ProfileData:
    id: str
    bio: str
    coverImageUrl: str
    createdAt: datetime
    dateOfBirth: datetime
    displayName: str
    location: str
    profileImageUrl: str
    username: str
    website: str

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", ""),
            bio=data.get("bio", ""),
            coverImageUrl=data.get("coverImageUrl", ""),
            createdAt=data.get("createdAt", None),
            dateOfBirth=data.get("dateOfBirth", None),
            displayName=data.get("displayName", ""),
            location=data.get("location", ""),
            profileImageUrl=data.get("profileImageUrl", ""),
            username=data.get("username", ""),
            website=data.get("website", ""),
        )

    @classmethod
    def to_dict(cls, profile):
        return {
            "id": profile.id,
            "bio": profile.bio,
            "coverImageUrl": profile.coverImageUrl,
            "createdAt": profile.createdAt,
            "dateOfBirth": profile.dateOfBirth,
            "displayName": profile.displayName,
            "location": profile.location,
            "profileImageUrl": profile.profileImageUrl,
            "username": profile.username,
            "website": profile.website,
        }

    @classmethod
    def to_dict_without_id(cls, profile):
        return {
            "bio": profile.bio,
            "coverImageUrl": profile.coverImageUrl,
            "createdAt": profile.createdAt,
            "dateOfBirth": profile.dateOfBirth,
            "displayName": profile.displayName,
            "location": profile.location,
            "profileImageUrl": profile.profileImageUrl,
            "username": profile.username,
            "website": profile.website,
        }
