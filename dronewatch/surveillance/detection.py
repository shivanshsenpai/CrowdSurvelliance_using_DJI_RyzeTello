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
WEAPON_INPUT_SIZE = 416
WEAPON_YOLOV8_INPUT_SIZE = int(os.environ.get("WEAPON_YOLOV8_INPUT_SIZE", "768"))
WEAPON_CONF_THRESHOLD = 0.22
WEAPON_STRONG_CONF_THRESHOLD = 0.35
WEAPON_NMS_THRESHOLD = 0.35
WEAPON_ALERT_CONFIRM_FRAMES = 2
WEAPON_MIN_AREA_RATIO = 0.00025
WEAPON_YOLOV8_CLASSES = {"gun", "knife", "grenade"}
WEAPON_YOLOV8_CLASS_CONF_THRESHOLDS = {
    "gun": 0.22,
    "knife": 0.12,
    "grenade": 0.22,
}
WEAPON_YOLOV8_CLASS_STRONG_THRESHOLDS = {
    "gun": 0.35,
    "knife": 0.20,
    "grenade": 0.35,
}
WEAPON_YOLOV8_CLASS_MIN_AREA_RATIOS = {
    "gun": 0.00025,
    "knife": 0.00006,
    "grenade": 0.00020,
}
WEAPON_YOLOV8_PREDICT_CONF = min(WEAPON_YOLOV8_CLASS_CONF_THRESHOLDS.values())

# Performance tuning
YOLO_INPUT_SIZE = 320
DETECT_EVERY_N = 3
STARTUP_MEMORY_MATCH_THRESHOLD = 0.78

# ========================= MODEL PATHS =========================
# Models are stored one directory up from the dronewatch project root

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_ROOT = os.path.join(os.path.dirname(_BASE), "models")

PERSON_CFG = os.path.join(_MODEL_ROOT, "person_detection", "yolov4.cfg")
PERSON_WEIGHTS = os.path.join(_MODEL_ROOT, "person_detection", "yolov4.weights")
WEAPON_CFG = os.path.join(_MODEL_ROOT, "weapon_detection", "yolov3_testing.cfg")
WEAPON_WEIGHTS = os.path.join(_MODEL_ROOT, "weapon_detection", "yolov3_training_2000.weights")
WEAPON_YOLOV8_WEIGHTS = os.path.join(_MODEL_ROOT, "weapon_detection", "threat_yolov8n.pt")
FIRE_CFG = os.path.join(_MODEL_ROOT, "fire_detection", "yolov4-tiny_custom.cfg")
FIRE_WEIGHTS = os.path.join(_MODEL_ROOT, "fire_detection", "yolov4-tiny_custom_last.weights")

# ========================= GLOBAL MODEL STATE =========================

models_loaded = False
personNet = None
weaponNet = None
weaponYolo = None
weapon_model_backend = "none"
fireNet = None
person_output_layers = []
weapon_output_layers = []
fire_output_layers = []


# ========================= LOAD MODELS =========================

def load_models():
    """Load all YOLO models. Returns True on success."""
    global models_loaded, personNet, weaponNet, weaponYolo, weapon_model_backend, fireNet
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
        weaponYolo = None
        weapon_model_backend = "none"
        if os.path.exists(WEAPON_YOLOV8_WEIGHTS):
            try:
                from ultralytics import YOLO

                weaponYolo = YOLO(WEAPON_YOLOV8_WEIGHTS)
                weapon_model_backend = "yolov8n-threat"
                print("[INFO] Weapon model loaded: YOLOv8n threat detector")
            except Exception as e:
                print(f"[WARN] YOLOv8 weapon model unavailable: {e}")
                weaponYolo = None

        if weaponYolo is None:
            print("[INFO] Falling back to legacy YOLOv3 weapon model...")
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
            weapon_model_backend = "legacy-yolov3"

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

def _update_detection_quality(confidences):
    """Update live detection-quality metrics from accepted model confidences."""
    if confidences:
        state.detection_accuracy = round(
            (sum(confidences) / len(confidences)) * 100, 1
        )
        state.recent_detection_count = len(confidences)
    else:
        state.detection_accuracy = 0.0
        state.recent_detection_count = 0

    recent = list(state.confidence_values)[-30:]
    state.average_confidence = round(
        (sum(recent) / len(recent)) * 100, 1
    ) if recent else 0.0


def _clip_box(frame, x, y, bw, bh):
    h, w = frame.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(w, x + bw)
    y2 = min(h, y + bh)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _build_person_signature(frame, x, y, bw, bh):
    """Build a compact visual signature from the top of a person box."""
    clipped = _clip_box(frame, x, y, bw, bh)
    if clipped is None:
        return None

    x1, y1, x2, y2 = clipped
    upper_y2 = min(y2, y1 + max(1, int((y2 - y1) * 0.45)))
    crop = frame[y1:upper_y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
        return None

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    return {
        "hist": hist.astype("float32"),
        "aspect": float(crop.shape[1]) / max(float(crop.shape[0]), 1.0),
    }


def _signature_similarity(a, b):
    if not a or not b:
        return 0.0

    hist_score = cv2.compareHist(a["hist"], b["hist"], cv2.HISTCMP_CORREL)
    hist_score = max(0.0, min(1.0, float(hist_score)))
    aspect_gap = abs(a["aspect"] - b["aspect"]) / max(a["aspect"], b["aspect"], 1.0)
    aspect_score = 1.0 - min(1.0, aspect_gap)
    return (hist_score * 0.85) + (aspect_score * 0.15)


def _find_startup_memory_match(signature):
    best_slot = None
    best_score = 0.0
    for slot, remembered in enumerate(state.startup_people_signatures):
        score = _signature_similarity(signature, remembered)
        if score > best_score:
            best_slot = slot
            best_score = score

    if best_slot is not None and best_score >= STARTUP_MEMORY_MATCH_THRESHOLD:
        return best_slot
    return None


def _remember_startup_person(signature):
    if signature is None:
        return None
    if len(state.startup_people_signatures) >= state.startup_memory_limit:
        return None

    state.startup_people_signatures.append(signature)
    return len(state.startup_people_signatures) - 1

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
    new_ignored = {}
    new_memory_slots = {}
    new_people = 0
    cached_boxes = []
    accepted_confidences = []

    for i in indices:
        x, y, bw, bh = boxes[i]
        cx, cy = x + bw // 2, y + bh // 2
        conf = confidences[i]
        signature = _build_person_signature(frame, x, y, bw, bh)
        ignored = False
        memory_slot = None

        matched_id = None
        for pid, (px, py) in state.tracked_people.items():
            if abs(cx - px) < 50 and abs(cy - py) < 50:
                matched_id = pid
                ignored = state.tracked_people_ignored.get(pid, False)
                memory_slot = state.tracked_people_memory_slots.get(pid)
                break

        if matched_id is None:
            memory_slot = _find_startup_memory_match(signature)
            if memory_slot is not None:
                matched_id = -(memory_slot + 1)
                ignored = True
            elif state.startup_people_seen < state.startup_memory_limit:
                memory_slot = _remember_startup_person(signature)
                state.startup_people_seen += 1
                if memory_slot is not None:
                    matched_id = -(memory_slot + 1)
                    ignored = True
                else:
                    matched_id = state.next_startup_track_id
                    state.next_startup_track_id -= 1
                    ignored = True
            else:
                matched_id = state.next_person_id
                state.next_person_id += 1
                new_people += 1

        new_tracked[matched_id] = (cx, cy)
        new_ignored[matched_id] = ignored
        if memory_slot is not None:
            new_memory_slots[matched_id] = memory_slot

        # Draw bounding box
        color = (90, 180, 255) if ignored else (0, 255, 100)
        label_id = (
            f"START {memory_slot + 1:02d}"
            if ignored and memory_slot is not None
            else f"ID {matched_id}"
        )
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
        label = f"{label_id} {int(conf * 100)}%"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), color, -1)
        cv2.putText(frame, label, (x + 2, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        cached_boxes.append({
            "x": x, "y": y, "w": bw, "h": bh,
            "color": color, "label": label, "label_color": (0, 0, 0)
        })
        state.confidence_values.append(conf)
        accepted_confidences.append(conf)

    state.last_detection_boxes = cached_boxes
    state.tracked_people = new_tracked
    state.tracked_people_ignored = new_ignored
    state.tracked_people_memory_slots = new_memory_slots
    state.cumulative_count += new_people
    state.current_count = sum(1 for ignored in new_ignored.values() if not ignored)
    state.density_alert = state.current_count > DENSITY_THRESHOLD
    _update_detection_quality(accepted_confidences)

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


def _finalize_weapon_detection(
    frame, cached_boxes, accepted_confidences, weapon_seen, strong_weapon_seen
):
    """Update shared weapon alert state after any weapon detector runs."""
    state.last_detection_boxes = cached_boxes
    if strong_weapon_seen:
        state.weapon_detection_streak = WEAPON_ALERT_CONFIRM_FRAMES
    elif weapon_seen:
        state.weapon_detection_streak += 1
    else:
        state.weapon_detection_streak = 0

    weapon_detected = (
        weapon_seen
        and state.weapon_detection_streak >= WEAPON_ALERT_CONFIRM_FRAMES
    )
    state.weapon_alert = weapon_detected
    _update_detection_quality(accepted_confidences)

    if weapon_detected and time.time() - state.last_alert_time > 3:
        state.last_alert_time = time.time()
        alert = {
            "type": "weapon",
            "severity": "critical",
            "message": "WEAPON DETECTED IN FRAME!",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "count": 1,
        }
        state.alert_history.appendleft(alert)
        state.alert_counts["weapon"] += 1

    return frame


def _draw_weapon_box(frame, x, y, bw, bh, conf, class_name=None, strong=None):
    strong = conf >= WEAPON_STRONG_CONF_THRESHOLD if strong is None else strong
    color = (0, 0, 255) if strong else (0, 165, 255)
    label_prefix = "WEAPON" if strong else "WEAPON?"
    if class_name:
        label_prefix = f"{label_prefix} {class_name.upper()}"
    label = f"{label_prefix} {int(conf * 100)}%"

    cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(frame, (x, y - lh - 10), (x + lw + 4, y), color, -1)
    cv2.putText(
        frame, label, (x + 2, y - 5),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
    )

    return {
        "x": x, "y": y, "w": bw, "h": bh,
        "color": color, "label": label,
        "label_color": (255, 255, 255),
    }


def detect_weapons(frame):
    """Detect weapons, preferring YOLOv8n threat weights with YOLOv3 fallback."""
    if weaponYolo is not None:
        return _detect_weapons_yolov8(frame)
    return _detect_weapons_yolov3(frame)


def _detect_weapons_yolov8(frame):
    """Detect guns/knives/grenades with the newer Ultralytics YOLOv8 model."""
    h, w, _ = frame.shape
    results = weaponYolo.predict(
        source=frame,
        imgsz=WEAPON_YOLOV8_INPUT_SIZE,
        conf=WEAPON_YOLOV8_PREDICT_CONF,
        iou=WEAPON_NMS_THRESHOLD,
        device="cpu",
        max_det=12,
        augment=False,
        verbose=False,
    )

    weapon_seen = False
    strong_weapon_seen = False
    cached_boxes = []
    accepted_confidences = []
    names = getattr(weaponYolo, "names", {}) or {}

    if results:
        for det in results[0].boxes:
            conf = float(det.conf[0])
            class_id = int(det.cls[0])
            class_name = str(names.get(class_id, f"class-{class_id}")).strip()
            class_key = class_name.lower()
            if class_key not in WEAPON_YOLOV8_CLASSES:
                continue

            min_conf = WEAPON_YOLOV8_CLASS_CONF_THRESHOLDS.get(
                class_key, WEAPON_CONF_THRESHOLD
            )
            if conf < min_conf:
                continue

            x1, y1, x2, y2 = [int(round(v)) for v in det.xyxy[0].tolist()]
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))
            bw = max(0, x2 - x1)
            bh = max(0, y2 - y1)
            area_ratio = (bw * bh) / max(float(w * h), 1.0)
            min_area_ratio = WEAPON_YOLOV8_CLASS_MIN_AREA_RATIOS.get(
                class_key, WEAPON_MIN_AREA_RATIO
            )
            if bw <= 0 or bh <= 0 or area_ratio < min_area_ratio:
                continue

            is_strong = conf >= WEAPON_YOLOV8_CLASS_STRONG_THRESHOLDS.get(
                class_key, WEAPON_STRONG_CONF_THRESHOLD
            )
            weapon_seen = True
            strong_weapon_seen = strong_weapon_seen or is_strong
            cached_boxes.append(
                _draw_weapon_box(
                    frame, x1, y1, bw, bh, conf, class_name, strong=is_strong
                )
            )
            state.confidence_values.append(conf)
            accepted_confidences.append(conf)

    return _finalize_weapon_detection(
        frame, cached_boxes, accepted_confidences, weapon_seen, strong_weapon_seen
    )


def _detect_weapons_yolov3(frame):
    """Detect weapons using the legacy YOLOv3 detector."""
    h, w, _ = frame.shape
    blob = cv2.dnn.blobFromImage(
        frame, 1 / 255, (WEAPON_INPUT_SIZE, WEAPON_INPUT_SIZE),
        (0, 0, 0), swapRB=True, crop=False
    )
    weaponNet.setInput(blob)
    outs = weaponNet.forward(weapon_output_layers)

    boxes = []
    confidences = []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > WEAPON_CONF_THRESHOLD:
                cx = int(detection[0] * w)
                cy = int(detection[1] * h)
                bw = int(detection[2] * w)
                bh = int(detection[3] * h)
                area_ratio = (bw * bh) / max(float(w * h), 1.0)
                if area_ratio < WEAPON_MIN_AREA_RATIO:
                    continue
                x = int(cx - bw / 2)
                y = int(cy - bh / 2)
                boxes.append([x, y, bw, bh])
                confidences.append(float(confidence))

    weapon_seen = False
    strong_weapon_seen = False
    cached_boxes = []
    accepted_confidences = []
    if len(boxes) > 0:
        indices = cv2.dnn.NMSBoxes(
            boxes, confidences, WEAPON_CONF_THRESHOLD, WEAPON_NMS_THRESHOLD
        )
        if indices is not None and len(indices) > 0:
            for i in indices.flatten():
                weapon_seen = True
                x, y, bw, bh = boxes[i]
                conf = confidences[i]
                strong_weapon_seen = strong_weapon_seen or (
                    conf >= WEAPON_STRONG_CONF_THRESHOLD
                )
                cached_boxes.append(_draw_weapon_box(frame, x, y, bw, bh, conf))
                state.confidence_values.append(conf)
                accepted_confidences.append(conf)

    return _finalize_weapon_detection(
        frame, cached_boxes, accepted_confidences, weapon_seen, strong_weapon_seen
    )


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
    accepted_confidences = []
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
            accepted_confidences.append(conf)

    state.last_detection_boxes = cached_boxes
    state.fire_alert = fire_detected
    _update_detection_quality(accepted_confidences)

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
