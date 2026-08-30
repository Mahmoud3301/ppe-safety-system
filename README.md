# 🛡️ PPE Safety Detection & Monitoring System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python">
  <img src="https://img.shields.io/badge/YOLOv8-Ultralytics-red?style=for-the-badge">
  <img src="https://img.shields.io/badge/FastAPI-2.1-green?style=for-the-badge&logo=fastapi">
  <img src="https://img.shields.io/badge/SQLite-Database-lightblue?style=for-the-badge&logo=sqlite">
  <img src="https://img.shields.io/badge/TTS-AR%20%2B%20EN-orange?style=for-the-badge">
  <img src="https://img.shields.io/badge/Dashboard-Live%20Stream-purple?style=for-the-badge">
</p>

> **Real-time PPE violation detection system** using YOLOv8 + ByteTrack.  
> Detects missing safety equipment, fires **bilingual Arabic + English** audio alerts, logs violations with photos to a database, streams live video to the browser, and displays everything on a professional real-time dashboard with dark/light mode.

---

## 📋 Table of Contents

- [Features](#-features)
- [System Architecture](#-system-architecture)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Dataset Preparation & Training](#-dataset-preparation--training)
- [Quick Start](#-quick-start)
- [Dashboard Guide](#-dashboard-guide)
- [API Reference](#-api-reference)
- [Configuration](#-configuration)
- [Classes & Violations](#-classes--violations)
- [Troubleshooting](#-troubleshooting)
- [Arabic Guide دليل عربي](#-arabic-guide)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎯 **YOLOv8 Detection** | Custom-trained model (12 PPE classes) |
| 🔄 **ByteTrack Tracking** | Persistent worker ID tracking across frames |
| 🔊 **Bilingual TTS** | Arabic alert first, then English — simultaneously |
| 📸 **Auto Snapshots** | Violation frame images saved automatically with user_id |
| 🎥 **Live Dashboard Stream** | MJPEG video feed inside the browser dashboard |
| 🕹️ **Browser Detection Control** | Start/stop detection from the dashboard (video or camera) |
| 📊 **Real-Time Dashboard** | Dark/light mode, live KPIs, 4 chart types |
| 🗄️ **SQLite Database** | All violations logged with user_id, timestamp, photo |
| ⏱️ **Working Hours Tracking** | Session run time logged automatically |
| 💰 **Deduction System** | Apply/remove salary deductions per violation from dashboard |
| 👤 **User ID Tagging** | Every violation tagged with operator ID |
| 🚫 **No Fake Data** | Dashboard shows ONLY real detection results |
| 🖥️ **Headless Mode** | Runs without GUI (no `cv2.imshow`) |
| 📡 **REST API** | Full FastAPI backend with Swagger docs at `/docs` |

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   VIDEO / CAMERA SOURCE                      │
│         (video2.ts  /  webcam  /  IP cam)                    │
└──────────────────────┬───────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   YOLO v8 model  │  ← best.pt (custom trained)
              │   + ByteTrack    │
              └────────┬────────┘
                       │  detections + track_ids
              ┌────────▼────────────┐
              │   Zone Engine       │  ← polygon in/out test
              │   Violation Tracker │  ← cooldown + min_frames
              └────────┬────────────┘
                       │  confirmed violation
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
    Bilingual TTS   Snapshot     FastAPI Backend
    (AR then EN)   (.jpg file)   POST /api/violations
                                 PUT  /api/sessions
                                      │
                                 SQLite DB
                                 violations.db
                                      │
                              ┌───────▼──────┐
                              │  Dashboard   │
                              │  :8888       │
                              │  MJPEG feed  │
                              └──────────────┘
```

---

## 📁 Project Structure

```
ppe-safety-system/
│
├── 📄 config/
│   └── config.yaml                 # All system settings
│
├── 🔍 detection/
│   └── detect_and_track.py         # CLI detection (headless, bilingual TTS)
│
├── 🔊 alerts/
│   ├── alert_builder.py            # Builds AR + EN alert messages
│   └── tts.py                      # Bilingual TTS engine (gTTS + pygame)
│
├── 🖥️ backend/
│   ├── main.py                     # FastAPI server + MJPEG stream + detection control
│   └── schema.sql                  # SQLite schema (violations + sessions)
│
├── 🌐 dashboard/
│   ├── index.html                  # 6-page dashboard
│   └── static/
│       ├── css/dashboard.css       # Dark/light mode styles
│       └── js/dashboard.js         # Charts, tables, live stream, deductions
│
├── 📸 snapshots/                   # Violation photos (auto-saved)
├── 🎬 output/                      # Annotated output videos
├── violations.db                   # SQLite database (auto-created)
├── video2.ts                       # Test video
├── test_video.mp4                  # Alternative test video
└── requirements.txt                # Python dependencies
```

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- Ubuntu / Linux
- GPU (recommended) or CPU

### 1. Navigate to project
```bash
cd /home/mahmoud/Desktop/Factory_Project/ppe-safety-system
```

### 2. Activate virtual environment
```bash
source /home/mahmoud/ai_env/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Verify model exists
```bash
ls /home/mahmoud/Desktop/Factory_Project/runs/ppe_detection/weights/best.pt
```

---

## 🎯 Dataset Preparation & Training

قبل ما تشغّل النظام لازم يكون عندك موديل مدرّب. الخطوات دي بتحمّل الداتاسيت، تعمله augmentation للـ classes النادرة، وتحفظه في مجلد جديد اسمه **`PPEs_balanced`** جاهز للتدريب عليه.

### 📦 Dataset Source
🔗 [PPEs Dataset (ppes-kaxsi/8)](https://universe.roboflow.com/personal-protective-equipment/ppes-kaxsi/dataset/8) — ~12,000 صورة، 12 class، ترخيص CC BY 4.0

### 1. جهّز مفتاح الـ API
اعمل حساب مجاني على [roboflow.com](https://roboflow.com)، هات الـ API key من `Settings → API`، وحطه في ملف `.env`:
```bash
ROBOFLOW_API_KEY=your_roboflow_api_key_here
```

### 2. شغّل `prepare_data.py`
السكريبت ده بيعمل 3 حاجات على التوالي:
1. **تحميل** الداتاسيت من الرابط فوق (نسخة `version 8`)
2. **Augmentation** للـ classes النادرة (`no_glove`, `no_goggles`, `no_mask`, `no_shoes`, `no-suit`) باستخدام Albumentations — تغييرات إضاءة، blur، نويز كاميرا، ظلال، تدوير بسيط، بما يحاكي بيئة مصنع فعلية
3. **حفظ الناتج النهائي** في مجلد جديد اسمه `PPEs_balanced/` منفصل عن الداتا الخام

```bash
python prepare_data.py
```

الناتج:
```
PPEs_balanced/
├── data.yaml
├── train/
│   ├── images/     # يحتوي الصور الأصلية + النسخ المعدّلة (aug)
│   └── labels/
├── valid/
└── test/
```

### 3. درّب الموديل على الداتا المتوازنة
```bash
python train_on_balanced.py
```
هيدرّب `YOLOv8n` على `PPEs_balanced/data.yaml` ويحفظ النتيجة في:
```
./runs/ppe_detection/weights/best.pt
```

بعد ما يخلص التدريب، الموديل ده هو نفسه اللي المفروض يتحدد مساره في `config/config.yaml` تحت `model.weights_path` عشان يستخدمه `detect_and_track.py` و `backend/main.py`.

---

## ⚡ Quick Start

### Option A — Run from dashboard (recommended)

**Terminal 1:**
```bash
cd /home/mahmoud/Desktop/Factory_Project/ppe-safety-system
source /home/mahmoud/ai_env/bin/activate
python backend/main.py
```

Open browser → `http://localhost:8888` → click **🎥 Live View** → select source → **▶ Start**

---

### Option B — Run detection from terminal + open dashboard

**Terminal 1 — Backend:**
```bash
cd /home/mahmoud/Desktop/Factory_Project/ppe-safety-system
source /home/mahmoud/ai_env/bin/activate
python backend/main.py
```

**Terminal 2 — Detection:**
```bash
# Video file
python detection/detect_and_track.py --source video2.ts --user-id operator_01

# Live camera
python detection/detect_and_track.py --source 0 --user-id operator_01

# Silent (no TTS, faster)
python detection/detect_and_track.py --source video2.ts --user-id operator_01 --no-tts
```

**Browser:** `http://localhost:8888`

---

### If port 8888 is already in use
```bash
fuser -k 8888/tcp
python backend/main.py
```

---

## 📊 Dashboard Guide

### Pages

| Page | Description |
|---|---|
| **📊 Dashboard** | 8 KPI cards + 4 live charts + recent violations table |
| **🚨 Violations** | Full table with filters — severity, status, deduction, date range |
| **📈 Analytics** | Resolution rate + trend charts + PPE type breakdown |
| **⏱️ Working Hours** | Session log — real run time, frames, violations per session |
| **🎥 Live View** | MJPEG stream + start/stop controls + live stats |
| **📍 Zones** | Per-zone violation statistics |

---

### KPI Cards (Dashboard)

| Card | Shows |
|---|---|
| ⚠️ Total Violations | All-time violation count |
| 📅 Today | Violations detected today |
| 🔴 Critical | 3+ PPE items missing |
| ⏳ Unresolved | Open (not yet resolved) violations |
| 👷 Workers Flagged | Unique tracked worker IDs |
| ⏰ Working Hours Today | From session run time today |
| 💰 Deductions Applied | Violations with an active deduction |
| 🕐 Last Hour | Violations in the past 60 minutes |

> ⚠️ **All numbers are 0 until you run detection.** No fake data is ever shown.

---

### 🎥 Live View — How to Use

1. Click **🎥 Live View** in the sidebar
2. Select **Source Type**: 📁 Video File or 📷 Live Camera
3. Select the file (`video2.ts`, `test_video.mp4`) or camera index (0, 1, 2)
4. Enter your **User / Operator ID**
5. Choose audio: 🔊 AR + EN or 🔇 Silent
6. Click **▶ Start** — the MJPEG feed appears immediately
7. Watch real-time stats: Frames, Violations, Workers, FPS, Progress
8. Click **⏹ Stop** when done

> The live feed shows annotated frames (bounding boxes, labels, zones, HUD).

---

### 💰 Deduction System

1. Click any violation row (in Dashboard or Violations page)
2. A modal opens showing full violation details + violation photo
3. Enter the **Deduction Amount in EGP**
4. Click **💰 Apply Deduction**
5. The KPI card **Deductions Applied** updates immediately
6. To undo: reopen the violation → click **✕ Remove Deduction**

> Deductions are stored per-violation in the database with the amount in EGP.

---

### 🌙 Dark / Light Mode

Click the ☀️ / 🌙 icon in the top-right corner to toggle.  
Your preference is saved in browser `localStorage`.

---

## 🔌 API Reference

Base URL: `http://localhost:8888`  
Interactive docs: `http://localhost:8888/docs`

### Violations

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/violations` | Log new violation |
| `GET` | `/api/violations` | List violations (filterable) |
| `GET` | `/api/violations/{id}` | Get single violation |
| `PUT` | `/api/violations/{id}` | Update (resolve / deduction / notes) |
| `DELETE` | `/api/violations/{id}` | Delete violation |

### Stats

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stats` | Full dashboard stats (all real data) |
| `GET` | `/api/stats/live` | Live poll data — violations, deductions, detection status |

### Sessions & Working Hours

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions` | Start detection session |
| `PUT` | `/api/sessions/{id}` | End session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/working-hours` | Total working hours summary |

### Detection Control

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/detection/start` | Start detection in background (body: `source`, `user_id`, `no_tts`) |
| `POST` | `/api/detection/stop` | Stop detection |
| `GET` | `/api/detection/status` | Current status, stats, FPS, progress |
| `GET` | `/api/stream` | MJPEG live video stream |

### Files

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/snapshots/{filename}` | Serve violation snapshot image |

---

### API Examples

```bash
# Get stats
curl http://localhost:8888/api/stats

# Apply deduction of 100 EGP to violation #3
curl -X PUT http://localhost:8888/api/violations/3 \
  -H "Content-Type: application/json" \
  -d '{"deduction": 1, "deduction_amount": 100.0}'

# Remove deduction
curl -X PUT http://localhost:8888/api/violations/3 \
  -H "Content-Type: application/json" \
  -d '{"deduction": 0, "deduction_amount": 0}'

# Start detection via API
curl -X POST http://localhost:8888/api/detection/start \
  -H "Content-Type: application/json" \
  -d '{"source": "video2.ts", "user_id": "operator_01", "no_tts": false}'

# Stop detection
curl -X POST http://localhost:8888/api/detection/stop

# Get working hours
curl http://localhost:8888/api/working-hours
```

---

## ⚙️ Configuration

File: `config/config.yaml`

```yaml
# Model
model:
  weights_path: "../runs/ppe_detection/weights/best.pt"
  confidence_threshold: 0.45   # lower = more detections
  iou_threshold: 0.5
  image_size: 640
  device: "auto"               # auto, cpu, 0 (GPU)

# Alerts
alerts:
  cooldown_seconds: 10         # seconds before re-alerting same worker
  min_frames_for_alert: 5      # frames violation must appear before alert
  tts_enabled: true            # enable audio alerts
  save_snapshots: true         # save violation photos

# Backend
backend:
  host: "0.0.0.0"
  port: 8888

# Video (CLI default source)
video:
  source: "video2.ts"
  show_display: false          # headless (no GUI window)
```

---

## 🏷️ Classes & Violations

| ID | Name | Type |
|---|---|---|
| 0 | glove | ✅ PPE Present |
| 1 | goggles | ✅ PPE Present |
| 2 | helmet | ✅ PPE Present |
| 3 | mask | ✅ PPE Present |
| 4 | **no-suit** | 🚨 Violation |
| 5 | **no_glove** | 🚨 Violation |
| 6 | **no_goggles** | 🚨 Violation |
| 7 | **no_helmet** | 🚨 Violation |
| 8 | **no_mask** | 🚨 Violation |
| 9 | **no_shoes** | 🚨 Violation |
| 10 | shoes | ✅ PPE Present |
| 11 | suit | ✅ PPE Present |

### Severity Levels

| Level | Condition |
|---|---|
| 🟡 Single | 1 PPE item missing |
| 🔴 Multiple | 2 PPE items missing |
| 🔴 Critical | 3+ PPE items missing |

---

## 🔊 TTS Alert Examples

**Arabic (plays first):**
> "تحذير. العامل رقم 25 في Construction Zone A. لا يرتدي خوذة السلامة. يرجى الالتزام بمعدات السلامة فوراً."

**English (plays after):**
> "Warning. Worker number 25 in Construction Zone A. Not wearing safety helmet. Please wear safety equipment immediately."

---

## 🗄️ Database Schema

```sql
-- Violations table
violations (
    id, user_id, track_id, zone, severity,
    missing_items, alert_text, snapshot_path,
    timestamp, created_at, resolved, resolved_at,
    notes, deduction, deduction_amount
)

-- Working hours / session tracking
detection_sessions (
    id, user_id, source, started_at, ended_at,
    total_frames, violations_detected, is_live
)
```

Reset database (start fresh):
```bash
rm violations.db
python backend/main.py   # auto-recreates on startup
```

---

## 🐛 Troubleshooting

| Error | Solution |
|---|---|
| `Address already in use` | `fuser -k 8888/tcp` then restart |
| `cv2.imshow` error | Already fixed — system is fully headless |
| `Model not found` | Check `weights_path` in `config.yaml` |
| `No module named cv2` | `source /home/mahmoud/ai_env/bin/activate` |
| TTS not working | Requires internet (gTTS). Use `--no-tts` to skip |
| `Cannot open video source` | File must be in `ppe-safety-system/` directory |
| Deductions show 0 | Enter amount then click **💰 Apply Deduction** (no checkbox) |
| Dashboard shows all zeros | Run detection first — no fake data is shown |
| Live stream blank | Click ▶ Start in Live View page first |

---

## 🚀 Arabic Guide — الدليل العربي

### تشغيل النظام

**الخطوة 1 — تشغيل الخادم الخلفي (Terminal واحد كافٍ):**
```bash
cd /home/mahmoud/Desktop/Factory_Project/ppe-safety-system
source /home/mahmoud/ai_env/bin/activate
python backend/main.py
```

**الخطوة 2 — افتح المتصفح:**
```
http://localhost:8888
```

**الخطوة 3 — تشغيل الكشف من اللوحة:**
- اضغط **🎥 Live View** في القائمة الجانبية
- اختر المصدر (فيديو أو كاميرا)
- أدخل User ID
- اضغط **▶ Start**

### أو من Terminal (الطريقة القديمة):
```bash
python detection/detect_and_track.py --source video2.ts --user-id operator_01
```

### إذا ظهر خطأ "Address already in use":
```bash
fuser -k 8888/tcp
python backend/main.py
```

### صفحات اللوحة:
| الصفحة | الوصف |
|---|---|
| **Dashboard** | KPIs + رسوم بيانية + آخر المخالفات |
| **Violations** | جدول كامل + فلترة + حذف/حل |
| **Analytics** | تحليلات متقدمة + نسبة الحل |
| **Working Hours** | ساعات العمل الحقيقية لكل جلسة |
| **Live View** | بث مباشر + تحكم بالكشف من المتصفح |
| **Zones** | إحصائيات المناطق |

### نظام الخصومات:
1. اضغط على أي مخالفة
2. أدخل المبلغ (مثال: 50 جنيه)
3. اضغط **💰 Apply Deduction**
4. الرقم يُحدَّث فوراً في اللوحة

### الوضع الداكن/الفاتح:
اضغط على ☀️ أو 🌙 في أعلى يمين اللوحة.

---

*Built with ❤️ using YOLOv8 · FastAPI · ByteTrack · gTTS · Chart.js · MJPEG Streaming*
