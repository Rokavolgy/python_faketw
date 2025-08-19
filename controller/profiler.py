import threading
import time
import tracemalloc

lock = threading.Lock()


def track_execution_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = (end_time - start_time) * 1000  # Convert to milliseconds
        print(f"{func.__name__} took {elapsed_time:.2f} ms to execute.")
        return result

    return wrapper


def profile_memory(func):
    def wrapper(*args, **kwargs):
        with lock:  # Ensure thread-safe access
            tracemalloc.start()
            result = func(*args, **kwargs)
            current, peak = tracemalloc.get_traced_memory()
            print(f"Current memory usage: {current / 1024:.2f} KB; Peak: {peak / 1024:.2f} KB")
            tracemalloc.stop()
        return result

    return wrapper
