"""
DroneWatch — Background Video Capture Thread.
Captures frames from drone or webcam and runs YOLO detection.
"""

import time
import threading

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
MODE_DETECT_EVERY_N = {
    "human": 3,
    "weapon": 4,
    "fire": 3,
}

BATTERY_POLL_INTERVAL = 15.0
ALTITUDE_POLL_INTERVAL = 0.75
ALTITUDE_QUERY_INTERVAL = 3.0
TEMPERATURE_POLL_INTERVAL = 5.0

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


# ========================= DRONE TELEMETRY =========================

def _coerce_telemetry_int(value, minimum=None, maximum=None):
    """Convert Tello telemetry to int and reject impossible values."""
    if value is None:
        return None
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if minimum is not None and numeric < minimum:
        return None
    if maximum is not None and numeric > maximum:
        return None
    return numeric


def _call_tello_query(drone, method_name):
    """Run a Tello command-query while serialized with flight commands."""
    with drone_state.drone_command_lock:
        return getattr(drone, method_name)()


def _update_battery(drone):
    """Poll battery through the Tello command API, with state fallback."""
    battery = None
    try:
        battery = _coerce_telemetry_int(
            _call_tello_query(drone, "query_battery"), 0, 100
        )
    except Exception as e:
        state.telemetry_errors += 1
        print(f"[TELLO] Battery query failed: {e}")

    if battery is None:
        try:
            battery = _coerce_telemetry_int(drone.get_battery(), 0, 100)
        except Exception as e:
            state.telemetry_errors += 1
            print(f"[TELLO] Battery state read failed: {e}")

    if battery is not None:
        state.battery = battery
        state.last_battery_update = time.time()
        return True
    return False


def _update_altitude(drone, use_query=False):
    """Poll altitude from height state/query, falling back to TOF distance."""
    altitude = None

    try:
        altitude = _coerce_telemetry_int(drone.get_height(), 0, 3000)
    except Exception:
        altitude = None

    if (altitude is None or altitude <= 0) and use_query:
        try:
            altitude = _coerce_telemetry_int(
                _call_tello_query(drone, "query_height"), 0, 3000
            )
        except Exception as e:
            state.telemetry_errors += 1
            print(f"[TELLO] Height query failed: {e}")

    if altitude is None or altitude <= 0:
        try:
            tof = _coerce_telemetry_int(drone.get_distance_tof(), 1, 1000)
            if tof is not None:
                altitude = tof
        except Exception:
            pass

    if altitude is None or altitude <= 0:
        try:
            tof = _coerce_telemetry_int(
                _call_tello_query(drone, "query_distance_tof"), 1, 1000
            )
            if tof is not None:
                altitude = tof
        except Exception:
            pass

    if altitude is not None:
        state.altitude = altitude
        state.last_altitude_update = time.time()
        return True
    return False


def _update_temperature(drone):
    try:
        temperature = _coerce_telemetry_int(drone.get_temperature(), -20, 100)
    except Exception:
        temperature = None

    if temperature is None:
        try:
            temperature = _coerce_telemetry_int(
                _call_tello_query(drone, "query_temperature"), -20, 100
            )
        except Exception:
            pass

    if temperature is not None:
        state.temperature = temperature


def drone_telemetry_thread(drone):
    """Poll slow Tello telemetry outside the video frame loop."""
    next_battery = 0.0
    next_altitude = 0.0
    next_altitude_query = 0.0
    next_temperature = 0.0

    while state.running and not state.demo_mode:
        now = time.time()

        if now >= next_battery:
            _update_battery(drone)
            next_battery = now + BATTERY_POLL_INTERVAL

        if now >= next_altitude:
            use_query = now >= next_altitude_query
            _update_altitude(drone, use_query=use_query)
            next_altitude = now + ALTITUDE_POLL_INTERVAL
            if use_query:
                next_altitude_query = now + ALTITUDE_QUERY_INTERVAL

        if now >= next_temperature:
            _update_temperature(drone)
            next_temperature = now + TEMPERATURE_POLL_INTERVAL

        time.sleep(0.1)


# ========================= VIDEO CAPTURE THREAD =========================

def video_capture_thread():
    """Background thread that captures and processes frames."""
    from .detection import (
        detect_humans, detect_weapons, detect_fire, redraw_cached_boxes
    )

    drone = None
    cap = None

    if not DEMO_MODE:
        try:
            from djitellopy import Tello

            # Attempt drone connection in a background thread with hard timeout
            # (djitellopy's internal retries can hang for 20+ seconds)
            _drone_result = [None]  # mutable container for thread result
            _drone_error = [None]

            def _try_drone():
                try:
                    d = Tello()
                    d.connect()
                    d.streamon()
                    _drone_result[0] = d
                except Exception as e:
                    _drone_error[0] = e

            print("[INFO] Attempting drone connection (8s timeout)...")
            probe = threading.Thread(target=_try_drone, daemon=True)
            probe.start()
            probe.join(timeout=8)  # Hard 8-second cutoff

            if _drone_result[0] is not None:
                drone = _drone_result[0]
                state.connected = True
                drone_state.drone_instance = drone
                _update_battery(drone)
                _update_altitude(drone, use_query=True)
                telemetry = threading.Thread(
                    target=drone_telemetry_thread,
                    args=(drone,),
                    daemon=True,
                )
                telemetry.start()
                print("[INFO] Drone connected!")
            else:
                err = _drone_error[0] or "Connection timed out"
                print(f"[WARN] Drone not available: {err}")
                print("[INFO] Falling back to webcam demo mode...")
                state.demo_mode = True
        except ImportError:
            print("[WARN] djitellopy not installed — skipping drone")
            state.demo_mode = True

    if state.demo_mode or drone is None:
        # Try multiple camera indices on Windows (0, 1, 2)
        for cam_idx in (0, 1, 2):
            cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                print(f"[INFO] Webcam opened on index {cam_idx} for demo mode.")
                break
            cap.release()
            cap = None

        if cap is None:
            # Fallback: try without DirectShow backend
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("[WARN] No webcam found. Using synthetic frames.")
                cap.release()
                cap = None
            else:
                print("[INFO] Webcam opened (default backend) for demo mode.")

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
        detect_every_n = MODE_DETECT_EVERY_N.get(state.mode, DETECT_EVERY_N)
        run_detection = (state.frame_counter % detect_every_n == 0)

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
        state.connected = False
    if cap:
        cap.release()
