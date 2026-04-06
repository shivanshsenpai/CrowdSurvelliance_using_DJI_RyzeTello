"""
DroneWatch Surveillance App — Django AppConfig.
Starts the YOLO models and video capture thread on server startup.
"""

import sys
import threading
from django.apps import AppConfig


class SurveillanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'surveillance'
    verbose_name = 'DroneWatch Surveillance'

    def ready(self):
        """Called once when Django starts. Load models and start video thread."""
        # Avoid running twice in dev (autoreload spawns a child process)
        if 'runserver' in sys.argv and '--noreload' not in sys.argv:
            # In autoreload mode, only run in the reloader child process
            import os
            if os.environ.get('RUN_MAIN') != 'true':
                return

        from .detection import load_models
        from .video_thread import video_capture_thread
        from .drone_state import state

        print("[INFO] Loading YOLO models...")
        load_models()

        thread = threading.Thread(target=video_capture_thread, daemon=True)
        thread.start()

        print("=" * 60)
        print("  🛸 DroneWatch Dashboard (Django)")
        print(f"  Mode: {'DEMO' if state.demo_mode else 'LIVE'}")
        print(f"  Dashboard: http://localhost:8000")
        print("=" * 60)
