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
        import os

        # Only run startup logic for actual server processes
        is_runserver = 'runserver' in sys.argv
        is_daphne = 'daphne' in sys.argv or os.environ.get('DAPHNE_PROCESS')
        is_asgi_server = os.environ.get('ASGI_SERVER', '').lower() in ('1', 'true', 'yes')

        # Skip for management commands (migrate, makemigrations, shell, test, etc.)
        management_cmds = (
            'makemigrations', 'migrate', 'collectstatic', 'shell',
            'test', 'createsuperuser', 'check', 'showmigrations',
            'dbshell', 'inspectdb', 'flush', 'loaddata', 'dumpdata',
        )
        is_management = any(cmd in sys.argv for cmd in management_cmds)

        if is_management:
            return

        if not (is_runserver or is_daphne or is_asgi_server):
            return

        # Avoid running twice in dev (autoreload spawns a child process)
        if is_runserver and '--noreload' not in sys.argv:
            if os.environ.get('RUN_MAIN') != 'true':
                return

        from .detection import load_models
        from .video_thread import video_capture_thread
        from .drone_state import state

        def _ensure_default_superuser():
            try:
                from django.contrib.auth import get_user_model
                from django.db.utils import OperationalError, ProgrammingError

                User = get_user_model()
                user, _created = User.objects.get_or_create(
                    username="shiv",
                    defaults={
                        "is_staff": True,
                        "is_superuser": True,
                        "is_active": True,
                    },
                )
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.set_password("8449")
                user.save()
                print("[INFO] Admin user ready: shiv / 8449")
            except (OperationalError, ProgrammingError) as e:
                print(f"[WARN] Admin user not created yet: {e}")
                print("[WARN] Run 'python manage.py migrate' first")
            except Exception as e:
                print(f"[WARN] Admin user setup failed: {e}")

        print("[INFO] Loading YOLO models...")
        load_models()
        _ensure_default_superuser()

        thread = threading.Thread(target=video_capture_thread, daemon=True)
        thread.start()

        # Start analytics recorder after Django is fully initialized
        # (deferred to avoid "database during app initialization" warning)
        def _start_analytics():
            try:
                from .analytics import AnalyticsRecorder
                from . import analytics as analytics_module
                rec = AnalyticsRecorder()
                rec.start()
                analytics_module.recorder = rec
                print("[INFO] Analytics recorder started")
            except Exception as e:
                print(f"[WARN] Analytics recorder failed to start: {e}")
                print("[WARN] Run 'python manage.py migrate' to create the database")

        timer = threading.Timer(2.0, _start_analytics)
        timer.daemon = True
        timer.start()

        print("=" * 60)
        print("  DroneWatch Dashboard (Django)")
        print(f"  Mode: {'DEMO' if state.demo_mode else 'LIVE'}")
        print(f"  Dashboard: http://localhost:8000")
        print(f"  Analytics: http://localhost:8000/analytics")
        print("=" * 60)
