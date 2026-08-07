#!/usr/bin/env python3
"""
Memory leak detection script for the social media application.
Run this script to monitor memory usage and detect potential leaks.
"""

import gc
import os
import sys

import psutil

from memory_profiler import start_memory_profiling, stop_memory_profiling, memory_monitor

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_memory_test():
    """Run the application with memory monitoring enabled."""
    print("Starting memory leak detection for Social Media App")
    print("=" * 60)

    # Start memory profiling
    start_memory_profiling()

    try:
        # Import and run the application
        from PySide6.QtWidgets import QApplication
        from main_window import MainWindow

        # Create the application
        app = QApplication(sys.argv)

        # Enable memory monitoring
        def on_memory_warning(msg):
            print(f"\n🚨 MEMORY WARNING: {msg}")
            memory_monitor.print_memory_report()
            memory_monitor.force_garbage_collection()

        memory_monitor.memory_warning.connect(on_memory_warning)

        # Create and show the main window
        main_window = MainWindow()
        main_window.show()

        print("\n📊 Memory monitoring active. The app is now running.")
        print("📋 Use these commands in the console:")
        print("   - memory_monitor.print_memory_report() - Show detailed memory report")
        print("   - memory_monitor.force_garbage_collection() - Force garbage collection")
        print("   - gc.collect() - Manual garbage collection")
        print("   - Check the console for automatic memory warnings")

        # Run the application
        result = app.exec()

        # Final cleanup
        if hasattr(main_window, 'cleanup'):
            main_window.cleanup()

        # Clear image cache
        try:
            from controller.image_loader_task import ImageLoaderTask
            ImageLoaderTask.clear_cache()
        except ImportError:
            pass

        # Force final garbage collection
        collected = gc.collect()
        print(f"\nFinal cleanup: collected {collected} objects")

        return result

    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user")
        return 0
    except Exception as e:
        print(f"\nError running application: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        stop_memory_profiling()
        print("\nMemory monitoring stopped")


def analyze_memory_usage():
    """Analyze current memory usage without running the app."""
    print("Analyzing current memory usage...")

    process = psutil.Process()
    memory_info = process.memory_info()

    print(f"RSS Memory: {memory_info.rss / 1024 / 1024:.1f} MB")
    print(f"VMS Memory: {memory_info.vms / 1024 / 1024:.1f} MB")

    # Check for Python objects
    import gc
    objects = gc.get_objects()
    print(f"Total Python objects: {len(objects)}")

    # Count objects by type
    type_counts = {}
    for obj in objects:
        obj_type = type(obj).__name__
        type_counts[obj_type] = type_counts.get(obj_type, 0) + 1

    print("\nTop object types:")
    for obj_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {obj_type}: {count}")


def check_cache_sizes():
    """Check the sizes of various caches in the application."""
    print("Checking cache sizes...")

    try:
        # Check image cache
        from controller.image_loader_task import ImageLoaderTask
        cache_size = len(ImageLoaderTask.cache)
        print(f"Image cache size: {cache_size} images")

        if cache_size > 50:
            print("⚠️  Warning: Image cache is large. Consider clearing it.")
    except ImportError:
        print("Could not check image cache (module not imported)")

    try:
        # Check user info cache
        from controller.user_info_cache import user_info_cache
        user_cache_size = len(user_info_cache)
        print(f"User info cache size: {user_cache_size} users")

        if user_cache_size > 100:
            print("⚠️  Warning: User info cache is large.")
    except ImportError:
        print("Could not check user info cache (module not imported)")


def main():
    """Main function to run memory leak detection."""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "analyze":
            analyze_memory_usage()
        elif command == "cache":
            check_cache_sizes()
        elif command == "test":
            return run_memory_test()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: test, analyze, cache")
            return 1
    else:
        # Default: run the full memory test
        return run_memory_test()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
