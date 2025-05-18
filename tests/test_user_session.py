import unittest
from unittest.mock import MagicMock
from controller.user_session import UserSession
from modal.user import ProfileData


class TestUserSession(unittest.TestCase):
    def setUp(self):
        UserSession._instance = None
        self.user_session = UserSession()

    def test_singleton_pattern(self):
        """that UserSession implements singleton pattern correctly"""
        first_instance = UserSession()
        second_instance = UserSession()
        self.assertIs(first_instance, second_instance)

    def test_initial_state(self):
        """initial state of UserSession"""
        self.assertFalse(self.user_session.is_authenticated)
        self.assertFalse(self.user_session.has_profile_data)
        self.assertIsNone(self.user_session.user_id)
        self.assertIsNone(self.user_session.id_token)
        self.assertIsNone(self.user_session.refresh_token)
        self.assertIsNone(self.user_session._profile_data)
        self.assertIsNone(self.user_session.user_likes)

    def test_set_auth_data(self):
        """setting authentication data"""
        self.user_session.set_auth_data("test_user", "test_token", "test_refresh")
        self.assertTrue(self.user_session.is_authenticated)
        self.assertEqual(self.user_session.user_id, "test_user")
        self.assertEqual(self.user_session.id_token, "test_token")
        self.assertEqual(self.user_session.refresh_token, "test_refresh")

    def test_set_profile_data(self):
        """setting profile data"""
        profile_data = MagicMock(spec=ProfileData)
        self.user_session.set_profile_data(profile_data)
        self.assertTrue(self.user_session.has_profile_data)
        self.assertEqual(self.user_session.profile_data, profile_data)

    def test_profile_data_getter_setter(self):
        """property getter and setter"""
        profile_data = MagicMock(spec=ProfileData)
        self.user_session._profile_data = profile_data
        self.assertEqual(self.user_session.profile_data, profile_data)

        new_profile = MagicMock(spec=ProfileData)
        self.user_session.profile_data = new_profile
        self.assertEqual(self.user_session._profile_data, new_profile)

        with self.assertRaises(ValueError):
            self.user_session.profile_data = "invalid"

        with self.assertRaises(ValueError):
            self.user_session.profile_data = None

    def test_clear_session(self):
        self.user_session.set_auth_data("test_user", "test_token", "test_refresh")
        profile_data = MagicMock(spec=ProfileData)
        self.user_session.set_profile_data(profile_data)
        self.user_session.set_user_likes(["post1", "post2"])

        self.user_session.clear_session()

        self.assertFalse(self.user_session.is_authenticated)
        self.assertFalse(self.user_session.has_profile_data)
        self.assertIsNone(self.user_session.user_id)
        self.assertIsNone(self.user_session.id_token)
        self.assertIsNone(self.user_session.refresh_token)
        self.assertIsNone(self.user_session._profile_data)
        self.assertIsNone(self.user_session.user_likes)

    def test_user_likes_management(self):
        self.user_session.set_user_likes(["post1", "post2"])
        self.assertEqual(self.user_session.get_user_likes(), ["post1", "post2"])

        self.assertTrue(self.user_session.check_if_user_liked("post1"))
        self.assertFalse(self.user_session.check_if_user_liked("post3"))

        self.user_session.remove_user_like("post1")
        self.assertEqual(self.user_session.get_user_likes(), ["post2"])
        self.assertFalse(self.user_session.check_if_user_liked("post1"))

        self.user_session.add_user_like("post3")
        self.assertEqual(self.user_session.get_user_likes(), ["post2", "post3"])
        self.assertTrue(self.user_session.check_if_user_liked("post3"))

        self.user_session.user_likes = None
        self.user_session.add_user_like("post4")
        self.assertEqual(self.user_session.get_user_likes(), ["post4"])

    def test_safe_remove_like(self):
        """removing a non-existent like doesn't cause errors"""
        self.user_session.user_likes = None
        self.user_session.remove_user_like("non_existent")
        self.assertIsNone(self.user_session.get_user_likes())

        self.user_session.set_user_likes(["post1", "post2"])
        self.user_session.remove_user_like("non_existent")
        self.assertEqual(self.user_session.get_user_likes(), ["post1", "post2"])


if __name__ == '__main__':
    unittest.main()
