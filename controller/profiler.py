import logging
import os
import time

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
