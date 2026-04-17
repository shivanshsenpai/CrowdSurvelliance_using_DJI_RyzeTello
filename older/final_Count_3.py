"""
=========================================================
PROJECT TITLE:
AI BASED DRONE SURVEILLANCE SYSTEM FOR
CROWD, WEAPON AND FIRE DETECTION

TECHNOLOGIES USED:
- Python
- OpenCV
- YOLO (v3 / v4)
- DJI Tello SDK (djitellopy)
- Multithreading
- Computer Vision
- Real-time Object Detection

AUTHOR:
Shivansh Sharma

DESCRIPTION:
This project uses a DJI Tello drone integrated with
YOLO-based deep learning models to detect:
1. Human Crowd Density
2. Weapons
3. Fire hazards

It also monitors drone altitude and provides
real-time alerts using sound alarms.
=========================================================
"""

# ========================= IMPORTS =========================

# OpenCV for image processing and computer vision
import cv2

# NumPy for numerical operations
import numpy as np

# DJI Tello Python SDK
from djitellopy import Tello

# Windows-only sound alert library
import winsound

# Threading for non-blocking alarm sound
import threading

# Time module for delays and alert cooldowns
import time

# OS module for console configuration
import os


# ========================= CONSOLE CONFIGURATION =========================

# Expands console window for better real-time logs
# This helps during live drone feed monitoring
os.system("mode con cols=200 lines=60")


# ========================= GLOBAL MODE STATE =========================

# Stores the current detection mode
# Possible values: "human", "weapon", "fire"
choice = "human"


# ========================= YOLO CONFIGURATION =========================

# Input size for YOLO tiny models
whT = 320

# Minimum confidence threshold for detections
confThreshold = 0.2

# Non-Max Suppression threshold
nmsThreshold = 0.5

# Maximum allowed people before density alert triggers
densityThreshold = 10


# ========================= MODEL FILE PATHS =========================

# Human detection YOLOv4 configuration
person_cfg = "models/person_detection/yolov4.cfg"
person_weights = "models/person_detection/yolov4.weights"

# Weapon detection YOLOv3 configuration
weapon_cfg = "models/weapon_detection/yolov3_testing.cfg"
weapon_weights = "models/weapon_detection/yolov3_training_2000.weights"

# Fire detection YOLOv4-tiny configuration
fire_cfg = "models/fire_detection/yolov4-tiny_custom.cfg"
fire_weights = "models/fire_detection/yolov4-tiny_custom_last.weights"


# ========================= LOAD YOLO MODELS =========================

# Load person detection network
personNet = cv2.dnn.readNet(person_weights, person_cfg)

# Get all layer names
person_layers = personNet.getLayerNames()

# Get output layers only
person_output_layers = [
    person_layers[i - 1]
    for i in personNet.getUnconnectedOutLayers().flatten()
]


# Load weapon detection network
weaponNet = cv2.dnn.readNet(weapon_weights, weapon_cfg)
weapon_layers = weaponNet.getLayerNames()
weapon_output_layers = [
    weapon_layers[i - 1]
    for i in weaponNet.getUnconnectedOutLayers().flatten()
]


# Load fire detection network
fireNet = cv2.dnn.readNetFromDarknet(fire_cfg, fire_weights)
fire_layers = fireNet.getLayerNames()
fire_output_layers = [
    fire_layers[i - 1]
    for i in fireNet.getUnconnectedOutLayers().flatten()
]


# ========================= GLOBAL TRACKING VARIABLES =========================

# Dictionary to track people IDs and positions
tracked_people = {}

# Counter for assigning unique person IDs
next_person_id = 0

# Total people ever detected
cumulative_count = 0

# Currently visible people
current_count = 0

# YOLO class index for humans
human_index = 0


# ========================= ALERT CONTROL =========================

# Last alert timestamp
last_alert_time = 0

# Minimum gap between alerts (seconds)
ALERT_GAP = 3


# ========================= ALARM FUNCTION =========================

def beep():
    """
    Plays a loud alarm sound.
    Runs in a separate thread so detection
    does not freeze during sound playback.
    """
    for _ in range(6):
        winsound.Beep(5000, 350)


# ========================= MODE SELECTION TRACKBAR =========================

def choose(x):
    """
    Callback for OpenCV trackbar.
    Allows switching detection modes dynamically.
    """
    global choice
    choice = ["human", "weapon", "fire"][x]
    print(f"[INFO] Mode changed to {choice.upper()}")


# ========================= HUMAN DETECTION FUNCTION =========================

def detect_humans(frame):
    """
    Detects humans using YOLOv4.
    Assigns unique IDs and tracks people
    across frames to avoid duplicate counting.
    """

    global tracked_people
    global next_person_id
    global cumulative_count
    global current_count

    h, w, _ = frame.shape

    # Convert image to YOLO blob
    blob = cv2.dnn.blobFromImage(
        frame,
        0.00392,
        (416, 416),
        swapRB=True
    )

    personNet.setInput(blob)
    outputs = personNet.forward(person_output_layers)

    boxes = []
    confidences = []

    # Loop over detections
    for out in outputs:
        for det in out:
            scores = det[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            # Only consider human class
            if confidence > 0.5 and class_id == human_index:
                cx, cy = int(det[0]*w), int(det[1]*h)
                bw, bh = int(det[2]*w), int(det[3]*h)
                x = int(cx - bw / 2)
                y = int(cy - bh / 2)

                boxes.append([x, y, bw, bh])
                confidences.append(float(confidence))

    # Apply Non-Max Suppression
    indices = cv2.dnn.NMSBoxes(
        boxes,
        confidences,
        0.5,
        0.4
    )

    indices = indices.flatten() if len(indices) > 0 else []

    new_tracked = {}
    new_people = 0

    # Assign IDs and draw boxes
    for i in indices:
        x, y, bw, bh = boxes[i]
        cx, cy = x + bw // 2, y + bh // 2

        matched_id = None

        for pid, (px, py) in tracked_people.items():
            if abs(cx - px) < 50 and abs(cy - py) < 50:
                matched_id = pid
                break

        if matched_id is None:
            matched_id = next_person_id
            next_person_id += 1
            new_people += 1

        new_tracked[matched_id] = (cx, cy)

        cv2.rectangle(frame, (x, y), (x+bw, y+bh), (0,255,0), 2)
        cv2.putText(
            frame,
            f"ID {matched_id}",
            (x, y-8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255,255,255),
            2
        )

    tracked_people = new_tracked
    cumulative_count += new_people
    current_count = len(tracked_people)

    density_alert = current_count > densityThreshold

    return frame, cumulative_count, current_count, density_alert


# ========================= UI DRAWING FUNCTION =========================

def draw_ui(frame, altitude, total=None, current=None,
            density=False, weapon=False, fire=False):
    """
    Draws all UI elements on video frame.
    Displays mode, altitude, alerts and counts.
    """

    cv2.putText(
        frame,
        f"MODE: {choice.upper()}",
        (20,40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0,255,255),
        2
    )

    cv2.putText(
        frame,
        f"ALTITUDE: {altitude} cm",
        (20,80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255,255,255),
        2
    )

    # Remaining UI elements unchanged...
    cv2.imshow("Detection Output", frame)


# ========================= MAIN FUNCTION =========================

def main():
    """
    Main execution loop.
    Handles drone connection, frame processing,
    detection switching and alert handling.
    """

    global last_alert_time

    drone = Tello()
    drone.connect()
    drone.streamon()

    cv2.namedWindow("Detection Output", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Detection Output", 1280, 800)
    cv2.createTrackbar("Mode", "Detection Output", 0, 2, choose)

    try:
        while True:

            frame = drone.get_frame_read().frame
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            frame = cv2.resize(frame, (960,720))

            altitude = drone.get_height()
            print(f"[INFO] Altitude: {altitude} cm", end="\r")

            density = weapon = fire = False

            if choice == "human":
                frame, total, current, density = detect_humans(frame)
            elif choice == "weapon":
                frame, weapon = detect_weapons(frame)
            else:
                frame, fire = detect_fire(frame)

            draw_ui(frame, altitude)

            if (density or weapon or fire) and \
               time.time() - last_alert_time > ALERT_GAP:
                last_alert_time = time.time()
                threading.Thread(
                    target=beep,
                    daemon=True
                ).start()

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        drone.streamoff()
        cv2.destroyAllWindows()


# ========================= PROGRAM ENTRY =========================

if __name__ == "__main__":
    main()
