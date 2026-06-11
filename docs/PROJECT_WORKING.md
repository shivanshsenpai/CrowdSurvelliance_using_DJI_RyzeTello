# DroneWatch Project Working

DroneWatch is a Django + Channels web app for live drone/webcam surveillance.
It captures video, runs AI detection, streams the annotated feed to the browser,
and records analytics in SQLite.

## Runtime Flow

1. Start the app from `dronewatch/manage.py`.
2. Django loads settings, routes, templates, static files, and the surveillance app.
3. `SurveillanceConfig.ready()` loads the AI models and starts background threads.
4. The video thread tries to connect to a DJI Ryze Tello.
5. If the Tello is unavailable, the system switches to webcam demo mode.
6. Frames are resized to `960x720` and passed through the active detector.
7. Processed frames are stored in shared state.
8. Django Channels streams video over `/ws/video`.
9. Django Channels streams telemetry over `/ws/data`.
10. Browser JavaScript updates the dashboard, charts, alerts, and drone controls.
11. The analytics thread saves snapshots to SQLite every 5 seconds.

## Detection Modes

| Mode | Model | Purpose |
| --- | --- | --- |
| Human | YOLOv4 via OpenCV DNN | Count and track people |
| Weapon | YOLOv8n threat model | Detect gun, knife, grenade |
| Fire | YOLOv4-tiny via OpenCV DNN | Detect fire/smoke |

Weapon mode uses class-specific tuning. Knives use a lower confidence threshold
and smaller minimum box size because blades are thin and often less confident
than guns.

The dashboard defaults to a clean light theme. The header toggle restores the
older dark command-center look and saves the choice in the browser.

Weapon detection is tuned for laptop CPU use. It runs every fourth frame at
`640x640` by default. If knife detection needs more detail and the laptop can
handle it, launch with:

```powershell
$env:WEAPON_YOLOV8_INPUT_SIZE='768'
python manage.py runserver 127.0.0.1:8000 --noreload
```

## Main Files

| File | Role |
| --- | --- |
| `dronewatch/manage.py` | Django entry point |
| `surveillance/apps.py` | Startup hook for models and threads |
| `surveillance/video_thread.py` | Frame capture, demo mode, Tello telemetry |
| `surveillance/detection.py` | Human, weapon, and fire detection |
| `surveillance/consumers.py` | WebSocket video and data streams |
| `surveillance/views.py` | Pages, REST APIs, drone commands |
| `surveillance/models.py` | SQLite session and snapshot models |
| `surveillance/analytics.py` | Background recorder and report generation |

## Run Commands

```powershell
cd W:\humanDetect\dronewatch
python manage.py migrate
python manage.py runserver 127.0.0.1:8000 --noreload
```

For webcam-only testing:

```powershell
$env:DEMO='1'
python manage.py runserver 127.0.0.1:8000 --noreload
```
