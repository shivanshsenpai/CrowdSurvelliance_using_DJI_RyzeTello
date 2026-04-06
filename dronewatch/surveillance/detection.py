"""
DroneWatch — YOLO Detection Functions.
Loads all three YOLO models and provides detection functions for
human, weapon, and fire detection with centroid tracking.
"""

import os
import time
from datetime import datetime

import cv2
import numpy as np

from .drone_state import state

# ========================= CONFIGURATION =========================

CONF_THRESHOLD = 0.2
NMS_THRESHOLD = 0.5
DENSITY_THRESHOLD = 10
HUMAN_INDEX = 0
WHT = 320  # Input size for YOLO tiny models

# Performance tuning
YOLO_INPUT_SIZE = 320
DETECT_EVERY_N = 3

# ========================= MODEL PATHS =========================
# Models are stored one directory up from the dronewatch project root

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_ROOT = os.path.join(os.path.dirname(_BASE), "models")

PERSON_CFG = os.path.join(_MODEL_ROOT, "person_detection", "yolov4.cfg")
PERSON_WEIGHTS = os.path.join(_MODEL_ROOT, "person_detection", "yolov4.weights")
WEAPON_CFG = os.path.join(_MODEL_ROOT, "weapon_detection", "yolov3_testing.cfg")
WEAPON_WEIGHTS = os.path.join(_MODEL_ROOT, "weapon_detection", "yolov3_training_2000.weights")
FIRE_CFG = os.path.join(_MODEL_ROOT, "fire_detection", "yolov4-tiny_custom.cfg")
FIRE_WEIGHTS = os.path.join(_MODEL_ROOT, "fire_detection", "yolov4-tiny_custom_last.weights")

# ========================= GLOBAL MODEL STATE =========================

models_loaded = False
personNet = None
weaponNet = None
fireNet = None
person_output_layers = []
weapon_output_layers = []
fire_output_layers = []


# ========================= LOAD MODELS =========================

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
    blob = cv2.dnn.blobFromImage(
        frame, 0.00392, (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE),
        (0, 0, 0), True, crop=False
    )
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
        label = f"ID {matched_id} {int(conf * 100)}%"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), (0, 255, 100), -1)
        cv2.putText(frame, label, (x + 2, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        cached_boxes.append({
            "x": x, "y": y, "w": bw, "h": bh,
            "color": (0, 255, 100), "label": label, "label_color": (0, 0, 0)
        })
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
    blob = cv2.dnn.blobFromImage(
        frame, 0.00392, (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE),
        (0, 0, 0), swapRB=True, crop=False
    )
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
                (lw, lh), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )
                cv2.rectangle(
                    frame, (x, y - lh - 10), (x + lw + 4, y), (0, 0, 255), -1
                )
                cv2.putText(
                    frame, label, (x + 2, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
                )
                cached_boxes.append({
                    "x": x, "y": y, "w": bw, "h": bh,
                    "color": (0, 0, 255), "label": label,
                    "label_color": (255, 255, 255)
                })
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
    blob = cv2.dnn.blobFromImage(
        frame, 1 / 255, (WHT, WHT), [0, 0, 0], crop=False
    )
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
            (lw, lh), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )
            cv2.rectangle(
                frame, (x, y - lh - 10), (x + lw + 4, y), (0, 100, 255), -1
            )
            cv2.putText(
                frame, label, (x + 2, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )
            cached_boxes.append({
                "x": x, "y": y, "w": bw, "h": bh,
                "color": (0, 100, 255), "label": label,
                "label_color": (255, 255, 255)
            })
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


# ========================= HELPERS =========================

def redraw_cached_boxes(frame):
    """Redraw cached detection boxes on a fresh frame (for skipped frames)."""
    for box in state.last_detection_boxes:
        x, y, bw, bh = box["x"], box["y"], box["w"], box["h"]
        color = box["color"]
        label = box["label"]
        label_color = box.get("label_color", (0, 0, 0))

        cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
        (lw, lh), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        )
        cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), color, -1)
        cv2.putText(
            frame, label, (x + 2, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, label_color, 1
        )
    return frame
