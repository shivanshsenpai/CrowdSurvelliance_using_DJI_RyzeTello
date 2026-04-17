import cv2
import numpy as np
from djitellopy import Tello
from collections import deque

# YOLO model paths
yolo_cfg = "models/yolov4.cfg"
yolo_weights = "models/yolov4.weights"
coco_names = "models/coco.names"

# Load YOLO model
net = cv2.dnn.readNet(yolo_weights, yolo_cfg)
layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

# Load COCO class labels
with open(coco_names, "r") as f:
    classes = f.read().strip().split("\n")

human_index = classes.index("person")

# Tracking dictionary for people
tracked_people = {}
next_person_id = 0  # Unique ID for new people
cumulative_count = 0
previous_frame_positions = []

# Function for YOLO-based human detection and tracking
def detect_humans(frame):
    global cumulative_count, tracked_people, next_person_id, previous_frame_positions

    height, width, _ = frame.shape
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
    net.setInput(blob)
    outputs = net.forward(output_layers)

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
    indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
    indices = indices.flatten() if len(indices) > 0 else []

    new_people_count = 0
    updated_tracked_people = {}

    # Track people using centroid tracking
    for i in indices:
        x, y, w, h = boxes[i]
        center_x, center_y = x + w // 2, y + h // 2

        matched_id = None
        for person_id, (px, py, pw, ph) in tracked_people.items():
            if abs(center_x - px) < 50 and abs(center_y - py) < 50:
                matched_id = person_id
                break

        if matched_id is None:
            matched_id = next_person_id
            next_person_id += 1
            new_people_count += 1

        updated_tracked_people[matched_id] = (center_x, center_y, w, h)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(frame, f"ID {matched_id}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    tracked_people = updated_tracked_people
    cumulative_count += new_people_count
    
    return frame, cumulative_count

# Function to draw people count on the frame
def draw_human_count(frame, count):
    cv2.putText(frame, f"Total People: {count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return frame

# Main function
def main():
    drone = Tello()
    drone.connect()
    drone.streamon()
    
    try:
        while True:
            frame = drone.get_frame_read().frame
            frame = cv2.resize(frame, (960, 720))
            
            # Detect humans and count them cumulatively
            frame_with_humans, human_count = detect_humans(frame)
            
            # Display human count
            final_frame = draw_human_count(frame_with_humans, human_count)
            
            # Show the final output
            cv2.imshow("Detection Output", final_frame)
            
            # Check for 'q' input in the terminal
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Landing drone...")
                if drone.is_flying:
                    drone.land()
                break
    finally:
        drone.streamoff()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
