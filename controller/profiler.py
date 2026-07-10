import logging
import os
import threading
import time
import tracemalloc

lock = threading.Lock()
PROFILING_ENABLED = os.environ.get("FWTTER_PROFILE") == "1"
logger = logging.getLogger(__name__)


def track_execution_time(func):
    def wrapper(*args, **kwargs):
        if not PROFILING_ENABLED:
            return func(*args, **kwargs)
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = (end_time - start_time) * 1000  # Convert to milliseconds
        logger.debug("%s took %.2f ms", func.__name__, elapsed_time)
        return result

    return wrapper


def profile_memory(func):
    def wrapper(*args, **kwargs):
        with lock:  # Ensure thread-safe access
            tracemalloc.start()
            result = func(*args, **kwargs)
            current, peak = tracemalloc.get_traced_memory()
            logger.debug(
                "Memory usage for %s: current %.2f KB; peak %.2f KB",
                func.__name__,
                current / 1024,
                peak / 1024,
            )
            tracemalloc.stop()
        return result

    return wrapper
