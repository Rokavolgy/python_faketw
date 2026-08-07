import importlib.util
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import GeoPoint

SCRIPT_PATH = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "tools"
        / "firestore_backup.py"
)
SPEC = importlib.util.spec_from_file_location("firestore_backup", SCRIPT_PATH)
firestore_backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(firestore_backup)


class TestFirestoreBackupCodec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = firestore.Client(
            project="demo-backup",
            credentials=AnonymousCredentials(),
        )

    def test_round_trip_preserves_firestore_types(self):
        timestamp = datetime(2026, 8, 6, 12, 30, tzinfo=timezone.utc)
        original = {
            "none": None,
            "bool": True,
            "integer": 2 ** 60,
            "float": 1.25,
            "nan": float("nan"),
            "text": "hello",
            "timestamp": timestamp,
            "point": GeoPoint(47.4979, 19.0402),
            "reference": self.database.document("posts/example"),
            "bytes": b"\x00\xff",
            "array": [1, {"__type__": "ordinary user field"}],
        }

        encoded = firestore_backup.encode_value(original)
        restored = firestore_backup.decode_value(encoded, self.database)

        self.assertIsNone(restored["none"])
        self.assertIs(restored["bool"], True)
        self.assertEqual(restored["integer"], 2 ** 60)
        self.assertEqual(restored["float"], 1.25)
        self.assertTrue(math.isnan(restored["nan"]))
        self.assertEqual(restored["text"], "hello")
        self.assertEqual(restored["timestamp"], timestamp)
        self.assertEqual(restored["point"], GeoPoint(47.4979, 19.0402))
        self.assertEqual(restored["reference"].path, "posts/example")
        self.assertEqual(restored["bytes"], b"\x00\xff")
        self.assertEqual(restored["array"][1]["__type__"], "ordinary user field")

    def test_rejects_unsupported_values(self):
        with self.assertRaises(TypeError):
            firestore_backup.encode_value(object())


if __name__ == "__main__":
    unittest.main()
