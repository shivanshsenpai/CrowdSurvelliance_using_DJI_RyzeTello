# 🛸 Crowd Surveillance using DJI Ryze Tello

An AI-powered real-time drone surveillance system built using Django, YOLO, and WebSockets for intelligent monitoring of crowds and environments.

## 🚀 Features

* 👥 Human Detection with tracking & crowd density alerts
* 🔫 Weapon Detection (real-time threat alerts)
* 🔥 Fire Detection system
* 📡 Live Drone Video Streaming (WebSockets)
* 📊 Real-time Dashboard with telemetry data
* 🧠 AI-powered detection using YOLO models

## 🧰 Tech Stack

* Backend: Django + Django Channels
* AI Models: YOLOv3, YOLOv4, YOLOv4-tiny
* Computer Vision: OpenCV
* Communication: WebSockets (Daphne ASGI server)
* Drone: DJI Ryze Tello

## ⚙️ Setup Instructions

1. Clone the repository:

```
git clone https://github.com/shivanshsenpai/CrowdSurvelliance_using_DJI_RyzeTello.git
cd CrowdSurvelliance_using_DJI_RyzeTello
```

2. Create virtual environment:

```
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
```

3. Install dependencies:

```
pip install -r requirements.txt
```

4. Download YOLO Models:
   👉 (Add Google Drive link here)

Place them inside:

```
/models/
```

5. Run server:

```
cd dronewatch
python manage.py runserver
```

## ⚠️ Note

YOLO model weights are not included due to size limitations. Please download them separately.

## 👨‍💻 Author

Shivansh Sharma
