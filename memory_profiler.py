"""
Memory leak detection and monitoring for the social media application.
This module provides tools to track memory usage and identify potential leaks.
"""

import gc
import tracemalloc
import weakref
from typing import Dict, List, Any

import psutil
from PySide6.QtCore import QTimer, QObject, Signal
from PySide6.QtWidgets import QWidget


class MemoryMonitor(QObject):
    """Monitor memory usage and detect potential leaks."""

    memory_warning = Signal(str)  # Emitted when memory usage is high

    def __init__(self, warning_threshold_mb=500):
        super().__init__()
        self.warning_threshold_mb = warning_threshold_mb
        self.process = psutil.Process()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_memory)
        self.baseline_memory = 0
        self.widget_refs = weakref.WeakSet()
        self.max_memory = 0

    def start_monitoring(self, interval_ms=5000):
        """Start monitoring memory usage every interval_ms milliseconds."""
        self.baseline_memory = self.get_memory_usage()
        self.timer.start(interval_ms)
        tracemalloc.start()
        print(f"Memory monitoring started. Baseline: {self.baseline_memory:.1f} MB")

    def stop_monitoring(self):
        """Stop memory monitoring."""
        self.timer.stop()
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        print("Memory monitoring stopped")

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        return self.process.memory_info().rss / 1024 / 1024

    def check_memory(self):
        """Check current memory usage and emit warning if high."""
        current_memory = self.get_memory_usage()

        if current_memory > self.max_memory:
            self.max_memory = current_memory

        growth = current_memory - self.baseline_memory

        print(f"Memory: {current_memory:.1f} MB (Growth: +{growth:.1f} MB, Max: {self.max_memory:.1f} MB)")

        if current_memory > self.warning_threshold_mb:
            warning_msg = f"High memory usage detected: {current_memory:.1f} MB"
            self.memory_warning.emit(warning_msg)
            print(f"WARNING: {warning_msg}")

    def register_widget(self, widget: QWidget):
        """Register a widget for tracking."""
        self.widget_refs.add(widget)

    def get_widget_count(self) -> int:
        """Get current number of tracked widgets."""
        return len(self.widget_refs)

    def force_garbage_collection(self):
        """Force garbage collection and report results."""
        print("Forcing garbage collection...")
        before_memory = self.get_memory_usage()
        collected = gc.collect()
        after_memory = self.get_memory_usage()
        freed = before_memory - after_memory
        print(f"GC collected {collected} objects, freed {freed:.1f} MB")
        return collected, freed

    def get_memory_snapshot(self) -> Dict[str, Any]:
        """Get a snapshot of current memory usage."""
        if not tracemalloc.is_tracing():
            return {"error": "Tracemalloc not started"}

        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')

        memory_info = {
            "current_memory_mb": self.get_memory_usage(),
            "widget_count": self.get_widget_count(),
            "top_memory_locations": []
        }

        for stat in top_stats[:10]:
            memory_info["top_memory_locations"].append({
                "file": stat.traceback.format()[0],
                "size_mb": stat.size / 1024 / 1024,
                "count": stat.count
            })

        return memory_info

    def print_memory_report(self):
        """Print a detailed memory report."""
        print("\n" + "=" * 60)
        print("MEMORY USAGE REPORT")
        print("=" * 60)

        snapshot = self.get_memory_snapshot()
        if "error" in snapshot:
            print(snapshot["error"])
            return

        print(f"Current Memory: {snapshot['current_memory_mb']:.1f} MB")
        print(f"Widget Count: {snapshot['widget_count']}")
        print(f"Memory Growth: +{snapshot['current_memory_mb'] - self.baseline_memory:.1f} MB")

        print("\nTop Memory Locations:")
        for i, location in enumerate(snapshot["top_memory_locations"], 1):
            print(f"{i:2d}. {location['file']}")
            print(f"    Size: {location['size_mb']:.2f} MB, Count: {location['count']}")

        print("=" * 60)


class ObjectTracker:
    """Track object creation and destruction."""

    def __init__(self):
        self.objects = {}

    def track_object(self, obj, name=None):
        """Start tracking an object."""
        obj_id = id(obj)
        obj_name = name or f"{obj.__class__.__name__}_{obj_id}"
        self.objects[obj_id] = {
            "name": obj_name,
            "class": obj.__class__.__name__,
            "ref": weakref.ref(obj, lambda ref: self._object_destroyed(obj_id))
        }
        print(f"Tracking object: {obj_name}")

    def _object_destroyed(self, obj_id):
        """Called when a tracked object is destroyed."""
        if obj_id in self.objects:
            obj_info = self.objects.pop(obj_id)
            print(f"Object destroyed: {obj_info['name']}")

    def get_alive_objects(self) -> List[Dict]:
        """Get list of objects still alive."""
        alive = []
        for obj_id, obj_info in list(self.objects.items()):
            if obj_info["ref"]() is not None:
                alive.append({
                    "id": obj_id,
                    "name": obj_info["name"],
                    "class": obj_info["class"]
                })
            else:
                # Object was destroyed but callback wasn't called
                del self.objects[obj_id]
        return alive

    def print_alive_objects(self):
        """Print all objects that are still alive."""
        alive = self.get_alive_objects()
        print(f"\nAlive objects: {len(alive)}")
        for obj in alive:
            print(f"  - {obj['name']} ({obj['class']})")


# Global instances
memory_monitor = MemoryMonitor()
object_tracker = ObjectTracker()


def start_memory_profiling():
    """Start memory profiling with default settings."""
    memory_monitor.start_monitoring(interval_ms=10000)  # Check every 10 seconds

    # Connect to warning signal
    memory_monitor.memory_warning.connect(
        lambda msg: print(f"🚨 MEMORY WARNING: {msg}")
    )

    print("Memory profiling started. Use these functions:")
    print("  - memory_monitor.print_memory_report()")
    print("  - memory_monitor.force_garbage_collection()")
    print("  - object_tracker.print_alive_objects()")


def stop_memory_profiling():
    """Stop memory profiling."""
    memory_monitor.stop_monitoring()
    print("Memory profiling stopped.")
