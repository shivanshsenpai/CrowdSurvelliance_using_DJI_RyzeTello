"""
DroneWatch — Global Drone State Container.
Thread-safe state shared between video capture thread, consumers, and views.
"""

import sys
import time
import threading
from collections import deque


import os

DEMO_MODE = "--demo" in sys.argv or os.environ.get("DEMO", "").strip() in ("1", "true", "yes")


class DroneState:
    """Thread-safe container for all drone/detection state."""

    def __init__(self):
        self.lock = threading.Lock()
        self.mode = "human"  # human, weapon, fire
        self.altitude = 0
        self.battery = 100
        self.signal = 100
        self.fps = 0.0
        self.temperature = 0

        # Detection counts
        self.current_count = 0
        self.cumulative_count = 0
        self.tracked_people = {}
        self.next_person_id = 0

        # Alert tracking
        self.density_alert = False
        self.weapon_alert = False
        self.fire_alert = False
        self.last_alert_time = 0
        self.alert_history = deque(maxlen=200)

        # Time-series for charts (timestamp, value)
        self.people_history = deque(maxlen=300)
        self.altitude_history = deque(maxlen=300)
        self.fps_history = deque(maxlen=300)
        self.confidence_values = deque(maxlen=100)

        # Alert counts by type
        self.alert_counts = {"density": 0, "weapon": 0, "fire": 0}

        # Connection
        self.connected = False
        self.demo_mode = DEMO_MODE
        self.frame = None
        self.processed_frame = None
        self.running = True

        # Frame skipping for performance
        self.frame_counter = 0
        self.last_detection_boxes = []  # cached boxes from last detection

        # Session
        self.session_start = time.time()
        self.total_frames = 0


# Global singleton
state = DroneState()
drone_instance = None  # Global ref so API can send commands
