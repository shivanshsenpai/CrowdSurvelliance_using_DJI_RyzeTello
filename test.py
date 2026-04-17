import cv2
import numpy as np
from djitellopy import Tello


# cap = cv2.VideoCapture(0)
whT = 320

confThreshold =0.2
nmsThreshold= 0.5

classesFile = "coco_fire.names"
# classesFile = "coco.names"
classNames = []
with open(classesFile, 'rt') as f:
    classNames = f.read().rstrip('\n').split('\n')
# print(classNames)
# print(len(classNames))

# modelConfiguration = "yolov3-tiny.cfg"
# modelWeights = "yolov3-tiny.weights"

# modelConfiguration = "yolov3.cfg"
# modelWeights = "yolov3.weights"

# modelConfiguration = "yolov3-tiny-obj.cfg"
# modelWeights = "yolov3-tiny-obj_final.weights"

# modelConfiguration = "yolov4-custom.cfg"
# modelWeights = "yolov4-custom_last.weights"

# modelConfiguration = "yolov4-tiny_custom.cfg"
# modelWeights = "yolov4-tiny_custom_last_2.weights"

modelConfiguration = "models/fire_detection/yolov4-tiny_custom.cfg"
modelWeights = "models/fire_detection/yolov4-tiny_custom_last.weights"


# net = cv2.dnn.readNet(modelConfiguration, modelWeights)
net = cv2.dnn.readNetFromDarknet(modelConfiguration, modelWeights)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
path = "E:/Daumn/1.PythonCode/Computervision/train_data/images/train/"

def findObjects(img):
    blob = cv2.dnn.blobFromImage(img, 1 / 255, (whT, whT), [0, 0, 0], crop=False)
    net.setInput(blob)
    layersNames = net.getLayerNames()
    # print(layersNames)
    if isinstance(net.getUnconnectedOutLayers(), np.ndarray):
        outputNames = [layersNames[i - 1] for i in net.getUnconnectedOutLayers().flatten()]
    else:
        outputNames = [layersNames[net.getUnconnectedOutLayers() - 1]]
    
    # print(outputNames)
    outputs = net.forward(outputNames)
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
        for i in indices.flatten():
            box = bbox[i]
            x, y, w, h = box[0], box[1], box[2], box[3]
            # print(x,y,w,h)
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 255), 2)
            cv2.putText(img, f'{classNames[classIds[i]].upper()} {int(confs[i] * 100)}%',
                       (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    
    return img

def main():
    drone = Tello()
    drone.connect()
    drone.streamon()

    while True:
        # success, img = cap.read()
        frame = drone.get_frame_read().frame
        frame = cv2.resize(frame, (960, 720))
        # img = cv2.imread(path+"img (56).jpg")
        
        # print(outputs[0].shape)
        # print(outputs[1].shape)
        # print(outputs[2].shape)
        # print(outputs[0][0])
        final_frame=findObjects(frame)
        final_frame = cv2.cvtColor(final_frame, cv2.COLOR_RGB2BGR)  # Convert frame to BGR format
        cv2.imshow("original", final_frame)

        if cv2.waitKey(1)==ord("q"):
            break

if __name__ == "__main__":
    main()