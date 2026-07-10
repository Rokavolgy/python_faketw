import os
import threading
from collections import OrderedDict


class MediaStore:
    """bounded cache for downloaded and decoded media."""

    _lock = threading.RLock()
    _media = OrderedDict()
    _media_bytes = 0
    _media_budget = 32 * 1024 * 1024

    _avif_frames = OrderedDict()
    _avif_bytes = 0
    _avif_budget = 96 * 1024 * 1024

    _inflight = {}
    _stats = {
        "media_hits": 0,
        "media_misses": 0,
        "coalesced_loads": 0,
        "avif_hits": 0,
        "avif_misses": 0,
    }

    @staticmethod
    def normalize_key(value):
        if not value:
            return ""
        value = str(value)
        if value.startswith(("avif:", "media:")):
            return value
        if "://" in value:
            return value.strip()
        return os.path.normcase(os.path.abspath(value))

    @classmethod
    def acquire_media_load(cls, key):
        """Return (state, payload, event) where state is cached, wait, or load."""
        key = cls.normalize_key(key)
        with cls._lock:
            entry = cls._media.get(key)
            if entry is not None:
                cls._media.move_to_end(key)
                cls._stats["media_hits"] += 1
                return "cached", entry[0], None

            event = cls._inflight.get(key)
            if event is not None:
                cls._stats["coalesced_loads"] += 1
                return "wait", None, event

            event = threading.Event()
            cls._inflight[key] = event
            cls._stats["media_misses"] += 1
            return "load", None, event

    @classmethod
    def wait_for_media(cls, key, event, timeout=30):
        if not event.wait(timeout):
            return None
        key = cls.normalize_key(key)
        with cls._lock:
            entry = cls._media.get(key)
            if entry is None:
                return getattr(event, "payload", None)
            cls._media.move_to_end(key)
            return entry[0]

    @classmethod
    def finish_media_load(cls, key, payload):
        key = cls.normalize_key(key)
        size = cls._estimate_payload_size(payload)
        with cls._lock:
            previous = cls._media.pop(key, None)
            if previous:
                cls._media_bytes -= previous[1]
            cls._media[key] = (payload, size)
            cls._media_bytes += size
            cls._evict_media_locked()
            event = cls._inflight.pop(key, None)
            if event:
                event.payload = payload
                event.set()

    @classmethod
    def fail_media_load(cls, key):
        key = cls.normalize_key(key)
        with cls._lock:
            event = cls._inflight.pop(key, None)
            if event:
                event.payload = None
                event.set()

    @classmethod
    def get_avif_frames(cls, key):
        key = cls.normalize_key(key)
        with cls._lock:
            entry = cls._avif_frames.get(key)
            if entry is None:
                cls._stats["avif_misses"] += 1
                return None
            cls._avif_frames.move_to_end(key)
            cls._stats["avif_hits"] += 1
            return entry[0]

    @classmethod
    def put_avif_frames(cls, key, frame_set, byte_size):
        key = cls.normalize_key(key)
        byte_size = max(0, int(byte_size))
        if byte_size > cls._avif_budget:
            return
        with cls._lock:
            previous = cls._avif_frames.pop(key, None)
            if previous:
                cls._avif_bytes -= previous[1]
            cls._avif_frames[key] = (frame_set, byte_size)
            cls._avif_bytes += byte_size
            while cls._avif_bytes > cls._avif_budget and cls._avif_frames:
                _, (_, removed_size) = cls._avif_frames.popitem(last=False)
                cls._avif_bytes -= removed_size

    @classmethod
    def clear(cls):
        with cls._lock:
            for event in cls._inflight.values():
                event.set()
            cls._inflight.clear()
            cls._media.clear()
            cls._avif_frames.clear()
            cls._media_bytes = 0
            cls._avif_bytes = 0

    @classmethod
    def stats(cls):
        with cls._lock:
            return {
                **cls._stats,
                "media_entries": len(cls._media),
                "media_bytes": cls._media_bytes,
                "avif_entries": len(cls._avif_frames),
                "avif_bytes": cls._avif_bytes,
                "inflight_loads": len(cls._inflight),
            }

    @classmethod
    def _evict_media_locked(cls):
        while cls._media_bytes > cls._media_budget and cls._media:
            _, (_, removed_size) = cls._media.popitem(last=False)
            cls._media_bytes -= removed_size

    @staticmethod
    def _estimate_payload_size(payload):
        if payload is None:
            return 0
        if isinstance(payload, (bytes, bytearray)):
            return len(payload)
        if isinstance(payload, tuple):
            return sum(
                len(value) if isinstance(value, (bytes, bytearray)) else 128
                for value in payload
            )
        try:
            return max(0, payload.width() * payload.height() * 4)
        except (AttributeError, TypeError):
            return 256
