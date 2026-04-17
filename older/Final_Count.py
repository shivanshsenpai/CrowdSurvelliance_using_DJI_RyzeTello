import cv2
import numpy as np
from djitellopy import Tello
import winsound
import threading
import time
import os

# ================= CONSOLE SETUP (WINDOWS) =================
os.system("mode con cols=200 lines=60")

# ================= GLOBAL MODE CHOICE =================
choice = "human"   # default mode

# ================= CONFIG =================
whT = 320
confThreshold = 0.2
nmsThreshold = 0.5
densityThreshold = 10

# ================= YOLO PATHS =================
person_cfg = "models/person_detection/yolov4.cfg"
person_weights = "models/person_detection/yolov4.weights"

weapon_cfg = "models/weapon_detection/yolov3_testing.cfg"
weapon_weights = "models/weapon_detection/yolov3_training_2000.weights"

fire_cfg = "models/fire_detection/yolov4-tiny_custom.cfg"
fire_weights = "models/fire_detection/yolov4-tiny_custom_last.weights"

# ================= LOAD MODELS =================
personNet = cv2.dnn.readNet(person_weights, person_cfg)
person_output_layers = [personNet.getLayerNames()[i - 1] for i in personNet.getUnconnectedOutLayers()]

weaponNet = cv2.dnn.readNet(weapon_weights, weapon_cfg)
weapon_output_layers = [weaponNet.getLayerNames()[i - 1] for i in weaponNet.getUnconnectedOutLayers()]

fireNet = cv2.dnn.readNetFromDarknet(fire_cfg, fire_weights)
fire_output_layers = [fireNet.getLayerNames()[i - 1] for i in fireNet.getUnconnectedOutLayers()]

# ================= GLOBAL STATE =================
tracked_people = {}
next_person_id = 0
cumulative_count = 0
current_count = 0
altitude = 0
human_index = 0

last_alert_time = 0
ALERT_GAP = 3  # seconds

# ================= BEEP =================
def beep():
    for _ in range(8):
        winsound.Beep(5000, 300)

# ================= TRACKBAR CALLBACK =================
def choose(x):
    global choice
    if x == 0:
        choice = "human"
    elif x == 1:
        choice = "weapon"
    else:
        choice = "fire"
    print(f"[INFO] Active Model: {choice.upper()}")

def nothing(x):
    pass

# ================= UI PANEL =================
def draw_panel(frame, x, y, w, h, alpha=0.6):
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

# ================= HUMAN DETECTION =================
def detect_humans(frame):
    global tracked_people, next_person_id, cumulative_count, current_count

    h, w, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), swapRB=True)
    personNet.setInput(blob)
    outputs = personNet.forward(person_output_layers)

    boxes, confidences = [], []

    for out in outputs:
        for det in out:
            scores = det[5:]
            cid = np.argmax(scores)
            conf = scores[cid]
            if conf > 0.5 and cid == human_index:
                cx, cy = int(det[0]*w), int(det[1]*h)
                bw, bh = int(det[2]*w), int(det[3]*h)
                x, y = int(cx-bw/2), int(cy-bh/2)
                boxes.append([x, y, bw, bh])
                confidences.append(float(conf))

    indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
    new_tracked = {}
    new_people = 0

    if len(indices) > 0:
        for i in indices.flatten():
            x, y, bw, bh = boxes[i]
            cx, cy = x + bw//2, y + bh//2

            pid_match = None
            for pid, (px, py) in tracked_people.items():
                if abs(cx - px) < 50 and abs(cy - py) < 50:
                    pid_match = pid
                    break

            if pid_match is None:
                pid_match = next_person_id
                next_person_id += 1
                new_people += 1

            new_tracked[pid_match] = (cx, cy)
            cv2.rectangle(frame, (x, y), (x+bw, y+bh), (0,255,0), 2)
            cv2.putText(frame, f"ID {pid_match}", (x, y-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)

    tracked_people = new_tracked
    cumulative_count += new_people
    current_count = len(tracked_people)

    return frame, cumulative_count, current_count, current_count > densityThreshold

# ================= WEAPON DETECTION =================
def detect_weapons(frame):
    h, w, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), swapRB=True)
    weaponNet.setInput(blob)
    outs = weaponNet.forward(weapon_output_layers)

    boxes, confs = [], []

    for out in outs:
        for det in out:
            scores = det[5:]
            conf = scores[np.argmax(scores)]
            if conf > 0.5:
                cx, cy = int(det[0]*w), int(det[1]*h)
                bw, bh = int(det[2]*w), int(det[3]*h)
                x, y = int(cx-bw/2), int(cy-bh/2)
                boxes.append([x, y, bw, bh])
                confs.append(float(conf))

    indexes = cv2.dnn.NMSBoxes(boxes, confs, 0.5, 0.4)
    weapon_alert = False

    if len(indexes) > 0:
        weapon_alert = True
        for i in indexes.flatten():
            x, y, bw, bh = boxes[i]
            cv2.rectangle(frame, (x,y),(x+bw,y+bh),(255,0,255),2)
            cv2.putText(frame,"WEAPON",(x,y-5),
                        cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,0,255),2)

    return frame, weapon_alert

# ================= FIRE DETECTION =================
def detect_fire(frame):
    blob = cv2.dnn.blobFromImage(frame, 1/255, (whT, whT))
    fireNet.setInput(blob)
    outs = fireNet.forward(fire_output_layers)

    h, w, _ = frame.shape
    fire_alert = False

    for out in outs:
        for det in out:
            scores = det[5:]
            conf = scores[np.argmax(scores)]
            if conf > confThreshold:
                fire_alert = True
                bw, bh = int(det[2]*w), int(det[3]*h)
                x = int(det[0]*w - bw/2)
                y = int(det[1]*h - bh/2)
                cv2.rectangle(frame,(x,y),(x+bw,y+bh),(0,0,255),2)
                cv2.putText(frame,"FIRE",(x,y-5),
                            cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,0,255),2)

    return frame, fire_alert

# ================= UI =================
def draw_ui(frame, total_count=None, current_count=None,
            density_alert=False, weapon_alert=False, fire_alert=False):

    h, w, _ = frame.shape
    draw_panel(frame, 0, 0, w, 60)
    cv2.putText(frame, f"MODE: {choice.upper()}",
                (20,40), cv2.FONT_HERSHEY_SIMPLEX,1,(0,255,255),2)

    y = 90
    if current_count is not None:
        cv2.putText(frame,f"Current People: {current_count}",(20,y),
                    cv2.FONT_HERSHEY_SIMPLEX,0.9,(255,255,0),2)
        y+=40

    if density_alert:
        cv2.putText(frame,"⚠ HIGH CROWD DENSITY",(20,y),
                    cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),3)
    if weapon_alert:
        cv2.putText(frame,"🔫 WEAPON DETECTED",(20,y+40),
                    cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),3)
    if fire_alert:
        cv2.putText(frame,"🔥 FIRE DETECTED",(20,y+80),
                    cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),3)

    cv2.imshow("Detection Output", frame)

# ================= MAIN =================
def main():
    global altitude, last_alert_time

    drone = Tello()
    drone.connect()
    drone.streamon()

    cv2.namedWindow("Detection Output", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Detection Output",
                          cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN)

    cv2.createTrackbar("choice","Detection Output",0,2,choose)

    try:
        while True:
            frame = drone.get_frame_read().frame

            # 🔥 COLOR FIX (MANDATORY)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            frame = cv2.resize(frame,(960,720))
            altitude = drone.get_height()

            density_alert = weapon_alert = fire_alert = False

            if choice == "human":
                frame, total, current, density_alert = detect_humans(frame)
            elif choice == "weapon":
                frame, weapon_alert = detect_weapons(frame)
            elif choice == "fire":
                frame, fire_alert = detect_fire(frame)

            draw_ui(frame,
                    current_count=current if choice=="human" else None,
                    density_alert=density_alert,
                    weapon_alert=weapon_alert,
                    fire_alert=fire_alert)

            if (density_alert or weapon_alert or fire_alert) and \
               time.time() - last_alert_time > ALERT_GAP:
                last_alert_time = time.time()
                threading.Thread(target=beep, daemon=True).start()

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        drone.streamoff()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
