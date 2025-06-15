from modal.user import ProfileData


class UserSession:
    _instance = None

    # profile_data: Optional[ProfileData] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UserSession, cls).__new__(cls)
            cls._instance.user_id = None
            cls._instance.id_token = None
            cls._instance.refresh_token = None
            cls._instance._profile_data = None
            cls._instance.user_likes = None
        return cls._instance

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    @property
    def has_profile_data(self) -> bool:
        return self._profile_data is not None

    def set_auth_data(self, user_id: str, id_token: str, refresh_token: str) -> None:
        self.user_id = user_id
        self.id_token = id_token
        self.refresh_token = refresh_token

    def set_profile_data(self, profile_data: ProfileData) -> None:
        self._profile_data = profile_data

    def clear_session(self) -> None:
        self.user_id = None
        self.id_token = None
        self.refresh_token = None
        self._profile_data = None
        self.user_likes = None

    def set_user_likes(self, user_likes: list) -> None:
        self.user_likes = user_likes

    def get_user_likes(self) -> list:
        return self.user_likes

    def remove_user_like(self, post_id: str) -> None:
        if self.user_likes and post_id in self.user_likes:
            self.user_likes.remove(post_id)

    def add_user_like(self, post_id: str) -> None:
        if self.user_likes is not None:
            self.user_likes.append(post_id)
        else:
            self.user_likes = [post_id]

    def check_if_user_liked(self, post_id: str) -> bool:
        if self.user_likes and post_id in self.user_likes:
            return True
        return False

    @property
    def profile_data(self):
        return self._profile_data

    @profile_data.setter
    def profile_data(self, data):
        from modal.user import ProfileData

        if data is None:
            raise ValueError("Profile data cannot be None")
        if isinstance(data, dict):

            try:
                print("Dictionary data:", data)
            except Exception:
                raise ValueError("i")
        elif isinstance(data, ProfileData):
            self._profile_data = data
        else:
            raise ValueError("profile data must be a ProfileData object")
