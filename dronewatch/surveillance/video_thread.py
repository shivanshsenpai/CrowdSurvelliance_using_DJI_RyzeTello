"""
DroneWatch — Background Video Capture Thread.
Captures frames from drone or webcam and runs YOLO detection.
"""

import time

import cv2
import numpy as np

from .drone_state import state, DEMO_MODE
from . import drone_state

# ========================= CONFIGURATION =========================

FRAME_WIDTH = 960
FRAME_HEIGHT = 720
WS_FPS = 20
DATA_FPS = 4
DETECT_EVERY_N = 3

# ========================= DEMO TELEMETRY =========================

demo_time_offset = 0


def generate_demo_telemetry():
    """Simulate drone telemetry (battery, altitude) for demo mode."""
    global demo_time_offset
    demo_time_offset += 1
    t = demo_time_offset * 0.1

    elapsed = time.time() - state.session_start
    state.battery = max(5, int(100 - elapsed * 0.15))
    state.altitude = int(50 + 30 * np.sin(t * 0.15))


# ========================= VIDEO CAPTURE THREAD =========================

def video_capture_thread():
    """Background thread that captures and processes frames."""
    from .detection import (
        models_loaded, detect_humans, detect_weapons,
        detect_fire, redraw_cached_boxes
    )

    drone = None
    cap = None

    if not DEMO_MODE:
        try:
            from djitellopy import Tello
            drone = Tello()
            drone.connect()
            drone.streamon()
            state.connected = True
            state.battery = drone.get_battery()
            drone_state.drone_instance = drone
            print("[INFO] Drone connected!")
        except Exception as e:
            print(f"[WARN] Drone not available: {e}")
            print("[INFO] Falling back to webcam demo mode...")
            state.demo_mode = True

    if state.demo_mode or drone is None:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[WARN] No webcam found. Using synthetic frames.")
            cap = None
        else:
            print("[INFO] Webcam opened for demo mode.")
        state.connected = True

    frame_time = 1.0 / WS_FPS
    data_time = 1.0 / DATA_FPS
    last_data_update = 0
    last_detected_frame = None

    while state.running:
        loop_start = time.time()

        # Capture frame
        if drone and not state.demo_mode:
            try:
                raw = drone.get_frame_read().frame
                raw = cv2.cvtColor(raw, cv2.COLOR_RGB2BGR)
                frame = cv2.resize(raw, (FRAME_WIDTH, FRAME_HEIGHT))
                state.altitude = drone.get_height()
                state.battery = drone.get_battery()
                state.temperature = drone.get_temperature()
            except Exception:
                frame = np.zeros(
                    (FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8
                )
        elif cap is not None:
            ret, frame = cap.read()
            if not ret:
                frame = np.zeros(
                    (FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8
                )
            else:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        else:
            frame = np.zeros(
                (FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8
            )
            noise = np.random.randint(
                5, 20, (FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8
            )
            frame = cv2.add(frame, noise)

        state.frame = frame.copy()
        state.frame_counter += 1

        # Skip-frame detection
        run_detection = (state.frame_counter % DETECT_EVERY_N == 0)

        # Re-import to get updated models_loaded value
        from .detection import models_loaded as _ml

        if _ml and run_detection:
            try:
                if state.mode == "human":
                    frame = detect_humans(frame)
                elif state.mode == "weapon":
                    frame = detect_weapons(frame)
                elif state.mode == "fire":
                    frame = detect_fire(frame)
                last_detected_frame = frame
            except Exception as e:
                print(f"[ERROR] Detection error: {e}")
        elif _ml and last_detected_frame is not None:
            frame = redraw_cached_boxes(frame)

        # Simulate telemetry in demo mode
        if state.demo_mode and drone is None:
            generate_demo_telemetry()

        state.processed_frame = frame
        state.total_frames += 1

        # Update time-series data
        now = time.time()
        if now - last_data_update > data_time:
            last_data_update = now
            ts = now - state.session_start
            state.people_history.append(
                {"t": round(ts, 1), "v": state.current_count}
            )
            state.altitude_history.append(
                {"t": round(ts, 1), "v": state.altitude}
            )
            state.fps_history.append(
                {"t": round(ts, 1), "v": round(state.fps, 1)}
            )

        # Calculate FPS
        elapsed = time.time() - loop_start
        state.fps = 1.0 / max(elapsed, 0.001)

        # Sleep to maintain target FPS
        sleep_time = frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Cleanup
    if drone and not state.demo_mode:
        try:
            drone.streamoff()
        except Exception:
            pass
    if cap:
        cap.release()
