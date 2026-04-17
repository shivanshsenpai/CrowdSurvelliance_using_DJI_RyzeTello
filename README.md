# 🛸 DroneWatch — AI-Powered Crowd Surveillance System

> Real-time crowd surveillance using DJI Ryze Tello drone with AI-powered human, weapon, and fire detection. Built with Django + Channels for WebSocket-based live streaming.

---

## 📋 Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Features](#features)
- [Complete Workflow](#complete-workflow)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Running the System](#running-the-system)
- [Detection Pipeline](#detection-pipeline)
- [API Reference](#api-reference)
- [Analytics Engine](#analytics-engine)
- [Configuration](#configuration)
- [Tech Stack](#tech-stack)

---

## Overview

DroneWatch is an AI-powered drone surveillance system that uses YOLOv4/v3 deep learning models to perform real-time detection of:

- **👤 Humans** — Crowd counting with centroid-based tracking and unique ID assignment
- **🔫 Weapons** — Threat detection with critical alert escalation
- **🔥 Fire** — Fire/smoke detection with emergency alerting

The system streams live video from a DJI Ryze Tello drone (or system webcam fallback) through a Django web dashboard with real-time WebSocket updates, interactive charts, drone flight controls, and a full analytics reporting engine.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  Dashboard    │  │  Analytics   │  │  Drone Controls    │    │
│  │  (index.html) │  │  (analytics) │  │  (REST API calls)  │    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘    │
│         │ WebSocket        │ HTTP               │ HTTP POST     │
└─────────┼──────────────────┼───────────────────┼───────────────┘
          │                  │                   │
          ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DJANGO + CHANNELS (ASGI)                      │
│                                                                  │
│  ┌──────────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │  WebSocket        │  │  REST API     │  │  Template Views │  │
│  │  Consumers        │  │  (views.py)   │  │  (HTML pages)   │  │
│  │  ├─ VideoConsumer │  │  ├─ status    │  │  ├─ dashboard   │  │
│  │  └─ DataConsumer  │  │  ├─ mode      │  │  └─ analytics   │  │
│  │                   │  │  ├─ alerts    │  │                 │  │
│  │                   │  │  ├─ drone/cmd │  │                 │  │
│  │                   │  │  └─ analytics │  │                 │  │
│  └────────┬─────────┘  └───────┬───────┘  └─────────────────┘  │
│           │                    │                                 │
│           ▼                    ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              SHARED STATE (drone_state.py)                │   │
│  │  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌────────────┐  │   │
│  │  │ Counts  │ │ Alerts   │ │ Telemetry │ │ Frame Data │  │   │
│  │  └─────────┘ └──────────┘ └───────────┘ └────────────┘  │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │                                       │
│  ┌──────────────────────┴───────────────────────────────────┐   │
│  │           VIDEO CAPTURE THREAD (video_thread.py)          │   │
│  │                                                           │   │
│  │  ┌─────────────────┐    ┌──────────────────────────────┐ │   │
│  │  │  Frame Source    │    │  YOLO Detection Pipeline     │ │   │
│  │  │  ├─ Tello Drone  │───▶│  ├─ detect_humans()         │ │   │
│  │  │  ├─ Webcam       │    │  ├─ detect_weapons()        │ │   │
│  │  │  └─ Synthetic    │    │  ├─ detect_fire()           │ │   │
│  │  └─────────────────┘    │  └─ redraw_cached_boxes()    │ │   │
│  │                          └──────────────────────────────┘ │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │         ANALYTICS RECORDER (analytics.py)                  │   │
│  │  ├─ Snapshots every 5s → SQLite DB                        │   │
│  │  ├─ Session tracking                                      │   │
│  │  └─ Report generation (trends, hourly, events)            │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

### 🎥 Live Video Streaming
- MJPEG frames streamed over WebSocket as base64-encoded JPEG
- 20 FPS target with automatic frame skipping for performance
- Detection overlays drawn directly on frames (bounding boxes, IDs, confidence)

### 🧠 AI Detection Modes
| Mode | Model | Purpose | Alert Type |
|------|-------|---------|------------|
| Human | YOLOv4 (320×320) | Crowd counting + density monitoring | High density (>10 people) |
| Weapon | YOLOv3 (320×320) | Threat detection | Critical |
| Fire | YOLOv4-tiny (320×320) | Fire/smoke detection | Critical |

### 🕹️ Drone Flight Controls
- Takeoff / Land / Emergency stop
- Directional movement (forward, back, left, right, up, down)
- Rotation (clockwise, counter-clockwise)
- Real-time battery, altitude, and temperature monitoring

### 📊 Analytics Engine
- Automatic snapshot recording every 5 seconds to SQLite database
- Session-based tracking with start/end times
- Hourly breakdown charts
- Crowd density trend analysis (increasing/decreasing/stable)
- High-density event detection and logging
- JSON export of full analysis reports

### 🔔 Alert System
- Real-time alert generation for density/weapon/fire events
- Alert severity levels (high, critical)
- Browser audio alerts with cooldown
- Visual flash overlay on video feed
- Filterable alert log (All, Density, Weapon, Fire)

---

## Complete Workflow

### Phase 1: Server Startup

```
python manage.py runserver 127.0.0.1:8000 --noreload
```

1. **Django initializes** → `SurveillanceConfig.ready()` fires
2. **YOLO models load** → Person (YOLOv4), Weapon (YOLOv3), Fire (YOLOv4-tiny)
3. **Video capture thread starts** (daemon thread):
   - Attempts drone connection (8-second timeout in background thread)
   - If drone responds → LIVE mode (drone feed)
   - If timeout/error → DEMO mode (system webcam fallback)
   - If no webcam → synthetic noise frames
4. **Analytics recorder starts** (deferred by 2s):
   - Creates a new `SurveillanceSession` in the database
   - Begins snapshotting crowd data every 5 seconds
5. **Server is ready** → Dashboard available at `http://localhost:8000`

### Phase 2: Frame Capture Loop

The video capture thread runs continuously at ~20 FPS:

```
┌──────────────────────────────────────────────┐
│                FRAME LOOP                     │
│                                               │
│  1. Capture frame from source                 │
│     ├─ Drone: drone.get_frame_read().frame    │
│     ├─ Webcam: cap.read()                     │
│     └─ Synthetic: numpy random noise          │
│                                               │
│  2. Resize to 960×720                         │
│                                               │
│  3. Detection (every 3rd frame):              │
│     ├─ Frame N: Run YOLO → draw boxes         │
│     ├─ Frame N+1: Redraw cached boxes         │
│     └─ Frame N+2: Redraw cached boxes         │
│                                               │
│  4. Update state:                             │
│     ├─ current_count, cumulative_count        │
│     ├─ tracked_people (centroid matching)      │
│     ├─ alert flags                            │
│     └─ confidence_values                      │
│                                               │
│  5. Store processed frame in state            │
│                                               │
│  6. Update time-series (every 250ms):         │
│     ├─ people_history                         │
│     ├─ altitude_history                       │
│     └─ fps_history                            │
│                                               │
│  7. Calculate FPS → sleep to match target     │
└──────────────────────────────────────────────┘
```

### Phase 3: WebSocket Streaming

When a browser connects to the dashboard:

1. **Video WebSocket** (`ws://host/ws/video`):
   - `VideoConsumer` accepts the connection
   - Continuously reads `state.processed_frame`
   - Encodes as JPEG (quality 70) → base64
   - Sends to browser at 20 FPS
   - Browser sets `<img>.src = "data:image/jpeg;base64,..."` for live display

2. **Data WebSocket** (`ws://host/ws/data`):
   - `DataConsumer` accepts the connection
   - Sends JSON telemetry at 4 Hz: counts, battery, altitude, FPS, alerts, chart data
   - Browser updates stats cards, charts (Chart.js), and alert log

### Phase 4: Detection Pipeline

#### Human Detection (YOLOv4)
```
Frame → Blob (320×320) → YOLOv4 → Filter class 0 (person)
    → NMS (threshold 0.4) → Centroid tracking
    → Match to existing IDs (within 50px radius)
    → If no match → assign new unique ID
    → Draw green bounding boxes with ID labels
    → Update cumulative count
    → Check density threshold (>10 = alert)
```

#### Weapon Detection (YOLOv3)
```
Frame → Blob (320×320) → YOLOv3 → Filter confidence > 0.5
    → NMS (threshold 0.4) → Draw red bounding boxes
    → Set weapon_alert flag → Generate critical alert
```

#### Fire Detection (YOLOv4-tiny)
```
Frame → Blob (320×320) → YOLOv4-tiny → Filter confidence > 0.2
    → NMS (threshold 0.5) → Draw orange bounding boxes
    → Set fire_alert flag → Generate critical alert
```

### Phase 5: Analytics Recording

Running in a background thread:
```
Every 5 seconds:
    → Read current detection state
    → Write CrowdSnapshot row to SQLite:
        - timestamp, people_count, cumulative_count
        - mode, density_alert, weapon_alert, fire_alert
    → Session is finalized on server shutdown:
        - peak_count, avg_count, total_unique, total_alerts
```

### Phase 6: Report Generation

When the analytics page is accessed:
```
Browser → GET /api/analytics/report
    → Query CrowdSnapshot table
    → Compute aggregates: peak, avg, min, total
    → Build hourly breakdown
    → Detect high-density events (periods where count ≥ 10)
    → Analyze trend (compare recent vs. earlier data)
    → Return full JSON report
    → Browser renders with Chart.js
```

---

## Project Structure

```
humanDetect/
├── dronewatch/                     # Django project root
│   ├── manage.py                   # Django management script
│   ├── db.sqlite3                  # SQLite database (auto-created)
│   │
│   ├── dronewatch/                 # Django project settings
│   │   ├── __init__.py
│   │   ├── settings.py             # Django config (Channels, static files)
│   │   ├── asgi.py                 # ASGI entry point (HTTP + WebSocket routing)
│   │   └── urls.py                 # Root URL config → includes surveillance.urls
│   │
│   └── surveillance/               # Main Django app
│       ├── __init__.py
│       ├── apps.py                 # AppConfig — startup logic (load models, start threads)
│       ├── models.py               # DB models: SurveillanceSession, CrowdSnapshot
│       ├── urls.py                 # URL routes: dashboard, analytics, API endpoints
│       ├── views.py                # REST API views + template views
│       ├── consumers.py            # WebSocket consumers: VideoConsumer, DataConsumer
│       ├── routing.py              # WebSocket URL routing
│       ├── drone_state.py          # Global shared state (thread-safe singleton)
│       ├── detection.py            # YOLO model loading + detection functions
│       ├── video_thread.py         # Background video capture thread
│       ├── analytics.py            # Analytics recorder + report generation
│       │
│       ├── templates/surveillance/
│       │   ├── index.html          # Main dashboard template
│       │   └── analytics.html      # Analytics report template
│       │
│       └── static/surveillance/
│           ├── style.css           # Dashboard styles (dark theme)
│           ├── app.js              # Dashboard client JS (WebSocket, charts)
│           ├── analytics.css       # Analytics page styles
│           ├── analytics.js        # Analytics client JS (report rendering)
│           └── vendor/             # Local assets (Chart.js, fonts)
│               ├── chart.umd.min.js
│               ├── fonts.css
│               ├── inter-*.ttf     # Inter font files
│               └── jetbrains-*.ttf # JetBrains Mono font files
│
├── models/                         # YOLO model files (not in git — too large)
│   ├── person_detection/
│   │   ├── yolov4.cfg
│   │   ├── yolov4.weights          # ~246 MB
│   │   └── coco.names
│   ├── weapon_detection/
│   │   ├── yolov3_testing.cfg
│   │   └── yolov3_training_2000.weights  # ~235 MB
│   └── fire_detection/
│       ├── yolov4-tiny_custom.cfg
│       └── yolov4-tiny_custom_last.weights  # ~22 MB
│
├── server.py                       # Legacy FastAPI server (standalone)
├── setup_models.py                 # Model download helper script
├── .gitignore
└── README.md
```

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- Webcam (for testing without drone)
- DJI Ryze Tello (optional)

### 1. Clone the repository
```bash
git clone https://github.com/shivanshsenpai/CrowdSurvelliance_using_DJI_RyzeTello.git
cd CrowdSurvelliance_using_DJI_RyzeTello
```

### 2. Create virtual environment
```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux/macOS
```

### 3. Install dependencies
```bash
pip install django channels daphne opencv-python numpy djitellopy
```

### 4. Download YOLO model weights

The model weights are too large for git. Download them manually:

```bash
python setup_models.py
```

Or download manually and place in the `models/` directory:
- **Person detection**: [YOLOv4 weights](https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4.weights) → `models/person_detection/yolov4.weights`
- **Weapon detection**: Custom-trained YOLOv3 → `models/weapon_detection/yolov3_training_2000.weights`
- **Fire detection**: Custom-trained YOLOv4-tiny → `models/fire_detection/yolov4-tiny_custom_last.weights`

### 5. Run database migrations
```bash
cd dronewatch
python manage.py migrate
```

### 6. Start the server
```bash
python manage.py runserver 127.0.0.1:8000 --noreload
```

Open `http://localhost:8000` in your browser.

---

## Running the System

### With Drone (Live Mode)
1. Power on the DJI Ryze Tello
2. Connect your computer to the Tello's WiFi network
3. Run: `python manage.py runserver 127.0.0.1:8000 --noreload`
4. The system will auto-detect the drone and switch to LIVE mode

### Without Drone (Demo/Webcam Mode)
The system automatically falls back to your system webcam:
```bash
# Auto-detect (tries drone for 8 seconds, then webcam)
python manage.py runserver 127.0.0.1:8000 --noreload

# Force webcam mode (skip drone detection entirely)
set DEMO=1 && python manage.py runserver 127.0.0.1:8000 --noreload
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard page |
| `/analytics` | GET | Analytics report page |
| `/api/status` | GET | System status (connected, mode, battery, fps) |
| `/api/mode/<mode>` | POST | Switch detection mode (human/weapon/fire) |
| `/api/alerts` | GET | Alert history and counts |
| `/api/drone/<cmd>` | POST | Send drone command (takeoff/land/up/down/etc.) |
| `/api/analytics/report` | GET | Full analysis report JSON |
| `/api/analytics/history` | GET | Time-series snapshot data |
| `/api/analytics/sessions` | GET | Past session list |

### WebSocket Endpoints

| Endpoint | Direction | Data |
|----------|-----------|------|
| `ws://host/ws/video` | Server → Client | Base64 JPEG frames (20 FPS) |
| `ws://host/ws/data` | Server → Client | JSON telemetry (4 Hz) |

---

## Analytics Engine

The analytics system records and analyzes crowd surveillance data:

### Data Collection
- **CrowdSnapshot** model: Timestamped readings every 5 seconds
  - `people_count`, `cumulative_count`, `mode`
  - `density_alert`, `weapon_alert`, `fire_alert`

### Report Contents
- **Summary**: Peak/avg/min counts, total unique people, alert totals
- **Trend**: "increasing" / "decreasing" / "stable" (compares recent vs. earlier data)
- **Hourly Breakdown**: Average and peak per hour
- **High-Density Events**: Periods where crowd count exceeded threshold
- **Timeline**: Full time-series for charting

### Viewing Reports
1. **Dashboard** → Click "📊 Analytics" button in the header
2. **API** → `GET /api/analytics/report` returns full JSON
3. **Export** → Click "📥 Export JSON" on the analytics page to download

---

## Configuration

Key configuration parameters in the codebase:

| Parameter | Default | Location | Description |
|-----------|---------|----------|-------------|
| `FRAME_WIDTH` | 960 | video_thread.py | Output frame width |
| `FRAME_HEIGHT` | 720 | video_thread.py | Output frame height |
| `WS_FPS` | 20 | video_thread.py | WebSocket video frame rate |
| `DATA_FPS` | 4 | consumers.py | Telemetry update rate |
| `DETECT_EVERY_N` | 3 | detection.py | Run YOLO every Nth frame |
| `YOLO_INPUT_SIZE` | 320 | detection.py | YOLO input resolution |
| `CONF_THRESHOLD` | 0.2 | detection.py | Minimum detection confidence |
| `NMS_THRESHOLD` | 0.5 | detection.py | Non-Maximum Suppression threshold |
| `DENSITY_THRESHOLD` | 10 | detection.py | People count for density alert |
| `SNAPSHOT_INTERVAL` | 5 | analytics.py | Seconds between DB snapshots |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend Framework | Django 5.1 + Channels 4.3 |
| ASGI Server | Daphne 4.2 |
| WebSocket | Django Channels (AsyncWebsocketConsumer) |
| Computer Vision | OpenCV 4.10 (DNN module) |
| Detection Models | YOLOv4, YOLOv3, YOLOv4-tiny |
| Drone SDK | djitellopy |
| Database | SQLite 3 |
| Frontend Charts | Chart.js |
| Fonts | Inter, JetBrains Mono (local, offline-ready) |
| Styling | Custom CSS (dark theme, glassmorphism) |

---

## Author

**Shivansh Sharma**

Built as part of the Crowd Surveillance using DJI Ryze Tello project.
