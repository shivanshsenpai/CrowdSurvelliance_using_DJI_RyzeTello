import cv2
import numpy as np
from djitellopy import Tello
from collections import deque
import winsound
import threading

whT = 320

confThreshold =0.2
nmsThreshold= 0.5

# YOLO model paths
person_cfg = "models/person_detection/yolov4.cfg"
person_weights = "models/person_detection/yolov4.weights"
weapon_cfg="models/weapon_detection/yolov3_testing.cfg"
weapon_weights="models/weapon_detection/yolov3_training_2000.weights"
fire_cfg = "models/fire_detection/yolov4-tiny_custom.cfg"
fire_weights = "models/fire_detection/yolov4-tiny_custom_last.weights"
# Load person YOLO model
personNet = cv2.dnn.readNet(person_weights, person_cfg)
person_layer_names = personNet.getLayerNames()
person_output_layers = [person_layer_names[i - 1] for i in personNet.getUnconnectedOutLayers()]

#Load weapon YOLO model
weaponNet = cv2.dnn.readNet(weapon_weights, weapon_cfg)
weaponNet.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
weaponNet.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
weapon_layer_names = weaponNet.getLayerNames()
try:
    weapon_output_layers = [weapon_layer_names[i - 1] for i in weaponNet.getUnconnectedOutLayers().flatten()]
except AttributeError:
    weapon_output_layers = [weapon_layer_names[i] for i in weaponNet.getUnconnectedOutLayers()]

# Load fire YOLO model
fireNet = cv2.dnn.readNetFromDarknet(fire_cfg, fire_weights)
fireNet.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
fireNet.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
fireLayersNames = fireNet.getLayerNames()
# print(layersNames)
if isinstance(fireNet.getUnconnectedOutLayers(), np.ndarray):
    fireOutputLayers = [fireLayersNames[i - 1] for i in fireNet.getUnconnectedOutLayers().flatten()]
else:
    fireOutputLayers = [fireLayersNames[fireNet.getUnconnectedOutLayers() - 1]]

human_index = 0
densityThreshold = 10  # Adjust as needed

# Tracking dictionary for people
tracked_people = {}  # Format: {ID: (x, y, w, h)}
next_person_id = 0  # Unique ID for new people
cumulative_count = 0
current_count=0
altitude=0
previous_frame_positions = []  # Stores positions of people in the previous frame

# Function for YOLO-based human detection and tracking
def detect_humans(frame):
    global cumulative_count,current_count, tracked_people, next_person_id, previous_frame_positions

    height, width, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
    personNet.setInput(blob)
    outputs = personNet.forward(person_output_layers)

    boxes = []
    confidences = []  
    current_frame_positions = []

    for output in outputs:
        for detection in output:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.5 and class_id == human_index:
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)
                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                current_frame_positions.append((center_x, center_y, w, h))

    # Apply Non-Maximum Suppression (NMS)
    if len(boxes) > 0:
        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        indices = indices.flatten() if len(indices) > 0 else []
    else:
        indices = []

    new_people_count = 0
    updated_tracked_people = {}

    # Track people using centroid tracking
    for i in indices:
        x, y, w, h = boxes[i]
        center_x, center_y = x + w // 2, y + h // 2

        matched_id = None
        for person_id, (px, py, pw, ph) in tracked_people.items():
            # Check if the detected person is close enough to an existing one
            if abs(center_x - px) < 50 and abs(center_y - py) < 50:
                matched_id = person_id
                break

        if matched_id is None:  # If no match found, it's a new person
            matched_id = next_person_id
            next_person_id += 1
            new_people_count += 1

        updated_tracked_people[matched_id] = (center_x, center_y, w, h)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)  # Draw bounding box
        cv2.putText(frame, f"ID {matched_id}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    tracked_people = updated_tracked_people
    cumulative_count += new_people_count  # Update total count
    current_count=len(indices) #update current count
    if current_count>densityThreshold:
        density_alert=True
    else:
        density_alert=False

    return frame, cumulative_count, current_count, density_alert

# For weapon detetction
def detect_weapons(frame):
    height, width, _ = frame.shape

    # Detect objects using YOLO
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), (0, 0, 0), swapRB=True, crop=False)
    weaponNet.setInput(blob)
    outs = weaponNet.forward(weapon_output_layers)

    # Initialize detection lists
    class_ids = []
    confidences = []
    boxes = []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence > 0.5:  # Confidence threshold
                # Object detected
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)

                # Calculate bounding box coordinates
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)

                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)

        # Apply Non-Maximum Suppression (NMS)
        indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)

        # ✅ Fix: Handle case when no objects are detected
        if indexes is not None and len(indexes) > 0:
            
            print("Weapon detected in frame!")

            for i in indexes.flatten():
                x, y, w, h = boxes[i]
                label = "weapon"
                color = (255, 20, 147)  # RGB for pink color

                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_PLAIN, 2, color, 2)
    weapon_alert=len(indexes)>0
    return frame,weapon_alert

def detect_fire(img):
    blob = cv2.dnn.blobFromImage(img, 1 / 255, (whT, whT), [0, 0, 0], crop=False)
    fireNet.setInput(blob)
    
    
    # print(outputNames)
    outputs = fireNet.forward(fireOutputLayers)
    hT, wT, cT = img.shape
    bbox = []
    classIds = []
    confs = []
    for output in outputs:
        for det in output:
            scores = det[5:]
            classId = np.argmax(scores)
            confidence = scores[classId]
            if confidence > confThreshold:
                w, h = int(det[2] * wT), int(  det[3] * hT)
                x, y = int((det[0] * wT) - w / 2), int((det[1] * hT) - h / 2)
                bbox.append([x, y, w, h])
                classIds.append(classId)
                confs.append(float(confidence))
    # print(len(bbox))
    indices = cv2.dnn.NMSBoxes(bbox, confs, confThreshold, nmsThreshold)
    # print(indices[0])

    if len(indices) > 0:
        print("Fire detected in frame!")
        for i in indices.flatten():
            box = bbox[i]
            x, y, w, h = box[0], box[1], box[2], box[3]
            # print(x,y,w,h)
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 255), 2)
            cv2.putText(img, f'FIRE {int(confs[i] * 100)}%',
                       (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    
    return img

# Function to draw people count on the frame
def draw_frame(frame,total_count, count,density_alert,weapon_alert):
    cv2.putText(frame, f"current People: {count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
    cv2.putText(frame, f"Total People: {total_count}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
    cv2.putText(frame, f"Altitude: {altitude}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255, 255), 2)

    alert_y=160

    if density_alert:
        cv2.putText(frame, "Alert: High Density!", (20, alert_y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0,255), 2)
        alert_y+=40

    if weapon_alert:
        cv2.putText(frame, "Alert: Weapon Detected!", (20, alert_y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0,255), 2)
        alert_y+=40
    
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)  # Convert frame to BGR format

    # Show the final output
    cv2.imshow("Detection Output", frame)

def beep():
    freq = 5000
    dur = 400

    # loop iterates 5 times i.e, 5 beeps will be produced.
    for i in range(0, 10):    
        winsound.Beep(freq, dur)

# Main function
def main():
    global altitude
    drone = Tello()
    drone.connect()
    drone.streamon()

    try:
        while True:
            frame = drone.get_frame_read().frame
            frame = cv2.resize(frame, (960, 720))
            altitude += drone.get_height()
            # Detect humans and count them cumulatively
            frame_with_humans,total_human_count, human_count,density_alert = detect_humans(frame)
            # Detect weapons
            frame_with_weapons_and_humans,weapon_alert = detect_weapons(frame_with_humans)
            # Detect fire
            frame_with_fire_and_weapons_and_humans = detect_fire(frame_with_weapons_and_humans)

            # Display human count
            draw_frame(frame_with_fire_and_weapons_and_humans,total_human_count, human_count,density_alert,weapon_alert)

            if density_alert:
                densityAlertThread=threading.Thread(target=beep)
                densityAlertThread.start()

            if weapon_alert:
                weaponAlertThread=threading.Thread(target=beep)
                weaponAlertThread.start()
            

            # Exit on pressing 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        drone.streamoff()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
