"""
=========================================================
DRONE SURVEILLANCE DASHBOARD — SERVER
=========================================================
FastAPI backend that serves the web dashboard and provides:
- WebSocket video stream with detection overlays
- WebSocket telemetry data (counts, alerts, altitude, battery, FPS)
- REST API for mode switching and status
- Demo mode with webcam fallback when drone is not connected

Usage:
    python server.py          # Try drone, fallback to webcam
    python server.py --demo   # Force demo mode (webcam/synthetic)
=========================================================
"""

import asyncio
import base64
import json
import sys
import time
import threading
import os
from collections import deque
from datetime import datetime

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ========================= CONFIGURATION =========================

DEMO_MODE = "--demo" in sys.argv
FRAME_WIDTH = 960
FRAME_HEIGHT = 720
WS_FPS = 20  # Target FPS for WebSocket video
DATA_FPS = 4  # Telemetry data updates per second

# YOLO thresholds
CONF_THRESHOLD = 0.2
NMS_THRESHOLD = 0.5
DENSITY_THRESHOLD = 10
HUMAN_INDEX = 0
WHT = 320  # Input size for YOLO tiny models

# Performance tuning
YOLO_INPUT_SIZE = 320   # Reduced from 416 — big speedup, minimal accuracy loss
DETECT_EVERY_N = 3      # Only run YOLO every Nth frame, reuse results in between

# ========================= MODEL PATHS =========================

PERSON_CFG = "models/person_detection/yolov4.cfg"
PERSON_WEIGHTS = "models/person_detection/yolov4.weights"
WEAPON_CFG = "models/weapon_detection/yolov3_testing.cfg"
WEAPON_WEIGHTS = "models/weapon_detection/yolov3_training_2000.weights"
FIRE_CFG = "models/fire_detection/yolov4-tiny_custom.cfg"
FIRE_WEIGHTS = "models/fire_detection/yolov4-tiny_custom_last.weights"

# ========================= GLOBAL STATE =========================

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


state = DroneState()
drone_instance = None  # Global ref so API can send commands

# ========================= LOAD YOLO MODELS =========================

models_loaded = False
personNet = None
weaponNet = None
fireNet = None
person_output_layers = []
weapon_output_layers = []
fire_output_layers = []


def load_models():
    """Load all YOLO models. Returns True on success."""
    global models_loaded, personNet, weaponNet, fireNet
    global person_output_layers, weapon_output_layers, fire_output_layers

    try:
        # Person detection
        print("[INFO] Loading person detection model...")
        personNet = cv2.dnn.readNet(PERSON_WEIGHTS, PERSON_CFG)
        personNet.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        personNet.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        layers = personNet.getLayerNames()
        person_output_layers = [
            layers[i - 1] for i in personNet.getUnconnectedOutLayers().flatten()
        ]

        # Weapon detection
        print("[INFO] Loading weapon detection model...")
        weaponNet = cv2.dnn.readNet(WEAPON_WEIGHTS, WEAPON_CFG)
        weaponNet.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
        weaponNet.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        layers = weaponNet.getLayerNames()
        try:
            weapon_output_layers_list = [
                layers[i - 1] for i in weaponNet.getUnconnectedOutLayers().flatten()
            ]
        except AttributeError:
            weapon_output_layers_list = [
                layers[i] for i in weaponNet.getUnconnectedOutLayers()
            ]
        weapon_output_layers.clear()
        weapon_output_layers.extend(weapon_output_layers_list)

        # Fire detection
        print("[INFO] Loading fire detection model...")
        fireNet = cv2.dnn.readNetFromDarknet(FIRE_CFG, FIRE_WEIGHTS)
        fireNet.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        fireNet.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        layers = fireNet.getLayerNames()
        if isinstance(fireNet.getUnconnectedOutLayers(), np.ndarray):
            fire_layers = [
                layers[i - 1] for i in fireNet.getUnconnectedOutLayers().flatten()
            ]
        else:
            fire_layers = [layers[fireNet.getUnconnectedOutLayers() - 1]]
        fire_output_layers.clear()
        fire_output_layers.extend(fire_layers)

        models_loaded = True
        print("[INFO] All models loaded successfully!")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to load models: {e}")
        models_loaded = False
        return False


# ========================= DETECTION FUNCTIONS =========================

def detect_humans(frame):
    """Detect humans using YOLOv4 with centroid tracking."""
    h, w, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE), (0, 0, 0), True, crop=False)
    personNet.setInput(blob)
    outputs = personNet.forward(person_output_layers)

    boxes = []
    confidences = []

    for output in outputs:
        for detection in output:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.5 and class_id == HUMAN_INDEX:
                cx = int(detection[0] * w)
                cy = int(detection[1] * h)
                bw = int(detection[2] * w)
                bh = int(detection[3] * h)
                x = int(cx - bw / 2)
                y = int(cy - bh / 2)
                boxes.append([x, y, bw, bh])
                confidences.append(float(confidence))

    indices = []
    if len(boxes) > 0:
        result = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        indices = result.flatten() if len(result) > 0 else []

    new_tracked = {}
    new_people = 0
    cached_boxes = []

    for i in indices:
        x, y, bw, bh = boxes[i]
        cx, cy = x + bw // 2, y + bh // 2
        conf = confidences[i]

        matched_id = None
        for pid, (px, py) in state.tracked_people.items():
            if abs(cx - px) < 50 and abs(cy - py) < 50:
                matched_id = pid
                break

        if matched_id is None:
            matched_id = state.next_person_id
            state.next_person_id += 1
            new_people += 1

        new_tracked[matched_id] = (cx, cy)

        # Draw bounding box
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 100), 2)
        # Label background
        label = f"ID {matched_id} {int(conf * 100)}%"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), (0, 255, 100), -1)
        cv2.putText(frame, label, (x + 2, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # Cache for skipped frames
        cached_boxes.append({"x": x, "y": y, "w": bw, "h": bh,
                             "color": (0, 255, 100), "label": label, "label_color": (0, 0, 0)})

        # Store confidence
        state.confidence_values.append(conf)

    state.last_detection_boxes = cached_boxes

    state.tracked_people = new_tracked
    state.cumulative_count += new_people
    state.current_count = len(new_tracked)
    state.density_alert = state.current_count > DENSITY_THRESHOLD

    if state.density_alert and time.time() - state.last_alert_time > 3:
        state.last_alert_time = time.time()
        alert = {
            "type": "density",
            "severity": "high",
            "message": f"High crowd density! {state.current_count} people detected",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "count": state.current_count,
        }
        state.alert_history.appendleft(alert)
        state.alert_counts["density"] += 1

    return frame


def detect_weapons(frame):
    """Detect weapons using YOLOv3."""
    h, w, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE), (0, 0, 0), swapRB=True, crop=False)
    weaponNet.setInput(blob)
    outs = weaponNet.forward(weapon_output_layers)

    boxes = []
    confidences = []
    class_ids = []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.5:
                cx = int(detection[0] * w)
                cy = int(detection[1] * h)
                bw = int(detection[2] * w)
                bh = int(detection[3] * h)
                x = int(cx - bw / 2)
                y = int(cy - bh / 2)
                boxes.append([x, y, bw, bh])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    # NMS moved OUTSIDE the loop (was a bug in original code)
    weapon_detected = False
    cached_boxes = []
    if len(boxes) > 0:
        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        if indices is not None and len(indices) > 0:
            weapon_detected = True
            for i in indices.flatten():
                x, y, bw, bh = boxes[i]
                conf = confidences[i]
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
                label = f"WEAPON {int(conf * 100)}%"
                (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), (0, 0, 255), -1)
                cv2.putText(frame, label, (x + 2, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cached_boxes.append({"x": x, "y": y, "w": bw, "h": bh,
                                     "color": (0, 0, 255), "label": label, "label_color": (255, 255, 255)})
                state.confidence_values.append(conf)

    state.last_detection_boxes = cached_boxes
    state.weapon_alert = weapon_detected

    if weapon_detected and time.time() - state.last_alert_time > 3:
        state.last_alert_time = time.time()
        alert = {
            "type": "weapon",
            "severity": "critical",
            "message": "⚠ WEAPON DETECTED IN FRAME!",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "count": 1,
        }
        state.alert_history.appendleft(alert)
        state.alert_counts["weapon"] += 1

    return frame


def detect_fire(frame):
    """Detect fire using YOLOv4-tiny."""
    blob = cv2.dnn.blobFromImage(frame, 1 / 255, (WHT, WHT), [0, 0, 0], crop=False)
    fireNet.setInput(blob)
    outputs = fireNet.forward(fire_output_layers)

    hT, wT, _ = frame.shape
    boxes = []
    confs = []
    class_ids = []

    for output in outputs:
        for det in output:
            scores = det[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > CONF_THRESHOLD:
                bw = int(det[2] * wT)
                bh = int(det[3] * hT)
                x = int((det[0] * wT) - bw / 2)
                y = int((det[1] * hT) - bh / 2)
                boxes.append([x, y, bw, bh])
                class_ids.append(class_id)
                confs.append(float(confidence))

    fire_detected = False
    cached_boxes = []
    indices = cv2.dnn.NMSBoxes(boxes, confs, CONF_THRESHOLD, NMS_THRESHOLD)

    if len(indices) > 0:
        fire_detected = True
        for i in indices.flatten():
            x, y, bw, bh = boxes[i]
            conf = confs[i]
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 100, 255), 2)
            label = f"FIRE {int(conf * 100)}%"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), (0, 100, 255), -1)
            cv2.putText(frame, label, (x + 2, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cached_boxes.append({"x": x, "y": y, "w": bw, "h": bh,
                                 "color": (0, 100, 255), "label": label, "label_color": (255, 255, 255)})
            state.confidence_values.append(conf)

    state.last_detection_boxes = cached_boxes
    state.fire_alert = fire_detected

    if fire_detected and time.time() - state.last_alert_time > 3:
        state.last_alert_time = time.time()
        alert = {
            "type": "fire",
            "severity": "critical",
            "message": "🔥 FIRE DETECTED IN FRAME!",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "count": 1,
        }
        state.alert_history.appendleft(alert)
        state.alert_counts["fire"] += 1

    return frame


# ========================= DEMO MODE SYNTHETIC DATA =========================

demo_time_offset = 0


def generate_demo_telemetry():
    """Simulate only drone telemetry (battery, altitude) for demo mode.
    Detection counts come from the REAL YOLO models running on webcam frames."""
    global demo_time_offset
    demo_time_offset += 1
    t = demo_time_offset * 0.1

    # Simulate battery drain
    elapsed = time.time() - state.session_start
    state.battery = max(5, int(100 - elapsed * 0.15))

    # Simulate altitude
    state.altitude = int(50 + 30 * np.sin(t * 0.15))


# draw_demo_overlay removed — we now always use real YOLO detection


def redraw_cached_boxes(frame):
    """Redraw cached detection boxes on a fresh frame (for skipped frames).
    This keeps bounding boxes visible while skipping expensive YOLO inference."""
    for box in state.last_detection_boxes:
        x, y, bw, bh = box["x"], box["y"], box["w"], box["h"]
        color = box["color"]
        label = box["label"]
        label_color = box.get("label_color", (0, 0, 0))

        cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), color, -1)
        cv2.putText(frame, label, (x + 2, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, label_color, 1)
    return frame


# ========================= VIDEO CAPTURE THREAD =========================

def video_capture_thread():
    """Background thread that captures and processes frames."""
    global drone_instance
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
            drone_instance = drone  # Store ref for API control
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
        state.connected = True  # "connected" in demo

    frame_time = 1.0 / WS_FPS
    data_time = 1.0 / DATA_FPS
    last_data_update = 0
    last_detected_frame = None  # Cache of last frame with detection overlays

    while state.running:
        loop_start = time.time()

        # Capture frame
        if drone and not state.demo_mode:
            try:
                raw = drone.get_frame_read().frame
                # Drone returns RGB — convert to BGR for OpenCV/YOLO pipeline
                raw = cv2.cvtColor(raw, cv2.COLOR_RGB2BGR)
                frame = cv2.resize(raw, (FRAME_WIDTH, FRAME_HEIGHT))
                state.altitude = drone.get_height()
                state.battery = drone.get_battery()
                state.temperature = drone.get_temperature()
            except Exception:
                frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        elif cap is not None:
            ret, frame = cap.read()
            if not ret:
                frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
            else:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        else:
            # Pure synthetic frame
            frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
            noise = np.random.randint(5, 20, (FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
            frame = cv2.add(frame, noise)

        state.frame = frame.copy()
        state.frame_counter += 1

        # Skip-frame detection: only run YOLO every Nth frame to boost FPS
        run_detection_this_frame = (state.frame_counter % DETECT_EVERY_N == 0)

        if models_loaded and run_detection_this_frame:
            try:
                if state.mode == "human":
                    frame = detect_humans(frame)
                elif state.mode == "weapon":
                    frame = detect_weapons(frame)
                elif state.mode == "fire":
                    frame = detect_fire(frame)
                last_detected_frame = frame  # Cache this for reuse
            except Exception as e:
                print(f"[ERROR] Detection error: {e}")
        elif models_loaded and last_detected_frame is not None:
            # Reuse last detection overlay blended onto current frame
            # Draw cached bounding boxes on the fresh frame for smooth video
            frame = redraw_cached_boxes(frame)

        # In demo mode, simulate telemetry (battery, altitude) since no real drone
        if state.demo_mode and drone is None:
            generate_demo_telemetry()

        state.processed_frame = frame
        state.total_frames += 1

        # Update time-series data
        now = time.time()
        if now - last_data_update > data_time:
            last_data_update = now
            ts = now - state.session_start
            state.people_history.append({"t": round(ts, 1), "v": state.current_count})
            state.altitude_history.append({"t": round(ts, 1), "v": state.altitude})
            state.fps_history.append({"t": round(ts, 1), "v": round(state.fps, 1)})

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


# ========================= FASTAPI APP =========================

app = FastAPI(title="DroneWatch Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static dashboard files
dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="static")


@app.get("/")
async def root():
    """Serve the dashboard."""
    return FileResponse(os.path.join(dashboard_dir, "index.html"))


@app.get("/api/status")
async def get_status():
    """Get current drone and system status."""
    return {
        "connected": state.connected,
        "demo_mode": state.demo_mode,
        "mode": state.mode,
        "battery": state.battery,
        "altitude": state.altitude,
        "fps": round(state.fps, 1),
        "uptime": round(time.time() - state.session_start),
        "total_frames": state.total_frames,
        "models_loaded": models_loaded,
    }


@app.post("/api/mode/{mode}")
async def set_mode(mode: str):
    """Switch detection mode."""
    if mode not in ("human", "weapon", "fire"):
        return JSONResponse({"error": "Invalid mode"}, status_code=400)
    state.mode = mode
    # Reset mode-specific state
    state.density_alert = False
    state.weapon_alert = False
    state.fire_alert = False
    state.current_count = 0
    state.tracked_people = {}
    print(f"[INFO] Mode switched to {mode.upper()}")
    return {"mode": mode}


@app.get("/api/alerts")
async def get_alerts():
    """Get alert history."""
    return {"alerts": list(state.alert_history), "counts": state.alert_counts}


MOVE_DISTANCE = 30  # cm per move command

@app.post("/api/drone/{cmd}")
async def drone_control(cmd: str):
    """Send a command to the drone."""
    if drone_instance is None:
        return JSONResponse({"error": "No drone connected (demo mode)"}, status_code=200)

    try:
        d = drone_instance
        if cmd == "takeoff":
            d.takeoff()
        elif cmd == "land":
            d.land()
        elif cmd == "emergency":
            d.emergency()
        elif cmd == "up":
            d.move_up(MOVE_DISTANCE)
        elif cmd == "down":
            d.move_down(MOVE_DISTANCE)
        elif cmd == "left":
            d.move_left(MOVE_DISTANCE)
        elif cmd == "right":
            d.move_right(MOVE_DISTANCE)
        elif cmd == "forward":
            d.move_forward(MOVE_DISTANCE)
        elif cmd == "back":
            d.move_back(MOVE_DISTANCE)
        elif cmd == "cw":
            d.rotate_clockwise(30)
        elif cmd == "ccw":
            d.rotate_counter_clockwise(30)
        else:
            return JSONResponse({"error": f"Unknown command: {cmd}"}, status_code=400)

        print(f"[DRONE] Command: {cmd}")
        return {"status": "ok", "command": cmd}
    except Exception as e:
        print(f"[DRONE] Command {cmd} failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=200)


@app.websocket("/ws/video")
async def video_websocket(websocket: WebSocket):
    """Stream MJPEG frames over WebSocket."""
    await websocket.accept()
    print("[WS] Video client connected")
    try:
        while state.running:
            if state.processed_frame is not None:
                _, buffer = cv2.imencode(
                    ".jpg", state.processed_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 70]
                )
                frame_b64 = base64.b64encode(buffer).decode("utf-8")
                await websocket.send_text(frame_b64)
            await asyncio.sleep(1.0 / WS_FPS)
    except WebSocketDisconnect:
        print("[WS] Video client disconnected")
    except Exception as e:
        print(f"[WS] Video error: {e}")


@app.websocket("/ws/data")
async def data_websocket(websocket: WebSocket):
    """Stream telemetry data over WebSocket."""
    await websocket.accept()
    print("[WS] Data client connected")
    try:
        while state.running:
            data = {
                "mode": state.mode,
                "battery": state.battery,
                "altitude": state.altitude,
                "fps": round(state.fps, 1),
                "current_count": state.current_count,
                "cumulative_count": state.cumulative_count,
                "density_alert": state.density_alert,
                "weapon_alert": state.weapon_alert,
                "fire_alert": state.fire_alert,
                "uptime": round(time.time() - state.session_start),
                "signal": state.signal,
                "alert_counts": state.alert_counts,
                "people_history": list(state.people_history)[-60:],
                "confidence_values": list(state.confidence_values)[-30:],
                "alerts": list(state.alert_history)[:20],
                "total_alerts": sum(state.alert_counts.values()),
            }
            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(1.0 / DATA_FPS)
    except WebSocketDisconnect:
        print("[WS] Data client disconnected")
    except Exception as e:
        print(f"[WS] Data error: {e}")


# ========================= STARTUP =========================

@app.on_event("startup")
async def startup():
    """Start video capture thread on app startup."""
    # Always load models — even in demo mode we run real detection on webcam
    print("[INFO] Loading YOLO models...")
    load_models()

    # Start capture thread
    thread = threading.Thread(target=video_capture_thread, daemon=True)
    thread.start()
    print("=" * 60)
    print("  🛸 DroneWatch Dashboard")
    print(f"  Mode: {'DEMO' if state.demo_mode else 'LIVE'}")
    print(f"  Dashboard: http://localhost:8000")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown():
    """Stop everything on shutdown."""
    state.running = False


# ========================= ENTRY POINT =========================

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
