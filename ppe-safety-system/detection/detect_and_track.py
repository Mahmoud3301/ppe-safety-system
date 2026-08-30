"""
Detection & Tracking Pipeline — PPE Safety System
===================================================
Main loop: YOLO detection + ByteTrack tracking + Zone logic + Alerts + TTS + Logging.
Processes video files or webcam feed.
- Headless operation (no cv2.imshow — works without display/GUI)
- Bilingual TTS alerts (Arabic then English simultaneously)
- Sends violations with snapshots and user_id to backend
- Tracks working hours via session API
- Real timestamps from actual run time
"""

import os
import sys
import cv2
import yaml
import time
import json
import requests
import numpy as np
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultralytics import YOLO
from alerts.alert_builder import build_alert, build_tts_texts
from alerts.tts import TTSEngine


# ─── Load Config ────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)


class ZoneEngine:
    """Determines if a person is inside a defined zone using polygon testing."""

    def __init__(self, zones_config):
        self.zones = []
        for zone in zones_config:
            self.zones.append({
                "name": zone["name"],
                "polygon": np.array(zone["polygon"], dtype=np.float32),
                "required_ppe": zone["required_ppe"],
                "severity": zone["severity"],
                "color": tuple(zone["color"]),
            })

    def check_person_in_zone(self, bbox_center, frame_w, frame_h):
        """Check which zone a person's center falls into. Returns zone info or None."""
        for zone in self.zones:
            poly = zone["polygon"].copy()
            poly[:, 0] *= frame_w
            poly[:, 1] *= frame_h
            poly = poly.astype(np.int32)
            result = cv2.pointPolygonTest(
                poly, (int(bbox_center[0]), int(bbox_center[1])), False
            )
            if result >= 0:
                return zone
        return None


class ViolationTracker:
    """Tracks violations per person to avoid duplicate alerts."""

    def __init__(self, cooldown_seconds=10, min_frames=5):
        self.cooldown = cooldown_seconds
        self.min_frames = min_frames
        self.violation_frames = defaultdict(lambda: defaultdict(int))
        self.last_alert_time = defaultdict(float)

    def update(self, track_id, violation_ids):
        """Update violation frame counts for a tracked person."""
        for vid in violation_ids:
            self.violation_frames[track_id][vid] += 1
        # Decay non-detected violations
        for vid in list(self.violation_frames[track_id].keys()):
            if vid not in violation_ids:
                self.violation_frames[track_id][vid] = max(0, self.violation_frames[track_id][vid] - 1)

    def should_alert(self, track_id):
        """Check if we should fire an alert for this person."""
        now = time.time()
        if now - self.last_alert_time[track_id] < self.cooldown:
            return False, []
        confirmed = [
            vid for vid, count in self.violation_frames[track_id].items()
            if count >= self.min_frames
        ]
        if confirmed:
            self.last_alert_time[track_id] = now
            for vid in confirmed:
                self.violation_frames[track_id][vid] = 0
            return True, confirmed
        return False, []


# ─── Backend Helpers ────────────────────────────────────────────────────────────

def start_session(user_id, source, is_live=False):
    """Register a detection session (for working hours tracking)."""
    try:
        url = f"http://localhost:{CONFIG['backend']['port']}/api/sessions"
        payload = {
            "user_id": user_id,
            "source": str(source),
            "started_at": datetime.now().isoformat(),
            "is_live": 1 if is_live else 0,
        }
        resp = requests.post(url, json=payload, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            print(f"   📋 Session started (ID: {data.get('session_id')})")
            return data.get("session_id")
    except Exception as e:
        print(f"   ⚠️  Could not start session: {e}")
    return None


def end_session(session_id, total_frames, violations_detected):
    """End a detection session with final stats."""
    if not session_id:
        return
    try:
        url = f"http://localhost:{CONFIG['backend']['port']}/api/sessions/{session_id}"
        payload = {
            "ended_at": datetime.now().isoformat(),
            "total_frames": total_frames,
            "violations_detected": violations_detected,
        }
        requests.put(url, json=payload, timeout=3)
        print(f"   ✅ Session ended — working hours logged")
    except Exception as e:
        print(f"   ⚠️  Could not end session: {e}")


def log_violation_to_backend(alert_data, snapshot_path=None, user_id="unknown"):
    """Send violation to FastAPI backend for logging."""
    try:
        url = f"http://localhost:{CONFIG['backend']['port']}/api/violations"
        # Normalize snapshot path to just filename for URL serving
        snap_name = ""
        if snapshot_path and os.path.exists(snapshot_path):
            snap_name = os.path.basename(snapshot_path)

        payload = {
            "user_id": user_id,
            "track_id": alert_data["track_id"],
            "zone": alert_data["zone"],
            "severity": alert_data["severity"],
            "missing_items": ", ".join(alert_data["missing_items"]),
            "alert_text": alert_data["text_en"],
            "timestamp": alert_data["timestamp"],
            "snapshot_path": snap_name,
        }
        resp = requests.post(url, json=payload, timeout=2)
        if resp.status_code == 200:
            vid_id = resp.json().get("id", "?")
            print(f"   📝 Logged to DB (violation #{vid_id})")
        else:
            print(f"   ⚠️  Backend returned {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"   ⚠️  Backend not running — violation not logged to DB")
    except Exception as e:
        print(f"   ⚠️  Logging error: {e}")


# ─── Drawing Helpers ────────────────────────────────────────────────────────────

def draw_zones(frame, zone_engine):
    """Draw zone polygons on the frame."""
    h, w = frame.shape[:2]
    for zone in zone_engine.zones:
        poly = zone["polygon"].copy()
        poly[:, 0] *= w
        poly[:, 1] *= h
        poly = poly.astype(np.int32)

        overlay = frame.copy()
        cv2.fillPoly(overlay, [poly], zone["color"])
        cv2.addWeighted(overlay, 0.1, frame, 0.9, 0, frame)
        cv2.polylines(frame, [poly], True, zone["color"], 2)
        cv2.putText(frame, zone["name"], (poly[0][0] + 10, poly[0][1] + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, zone["color"], 2)


def draw_hud(frame, frame_count, total_frames, stats, fps_actual, user_id):
    """Draw heads-up display on frame."""
    h, w = frame.shape[:2]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Top bar
    cv2.rectangle(frame, (0, 0), (w, 50), (10, 10, 30), -1)
    cv2.putText(frame, f"PPE Safety Monitor | {now_str} | User: {user_id}",
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    if total_frames > 0:
        progress = frame_count / total_frames * 100
        cv2.putText(frame, f"Frame: {frame_count}/{total_frames} ({progress:.1f}%)",
                    (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
    else:
        cv2.putText(frame, f"Frame: {frame_count} | FPS: {fps_actual:.1f}",
                    (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    # Bottom bar
    cv2.rectangle(frame, (0, h - 40), (w, h), (10, 10, 30), -1)
    status = (f"Violations: {stats['total_violations']} | "
              f"Alerts: {stats['alerts_fired']} | "
              f"Workers: {len(stats['worker_ids'])}")
    cv2.putText(frame, status, (10, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)


# ─── Main Detection Loop ────────────────────────────────────────────────────────

def run_detection(video_source=None, user_id="worker_01", no_display=True, no_tts=False):
    """
    Main detection loop.

    Args:
        video_source: Path to video file or camera index (int)
        user_id: Worker/operator ID for database logging
        no_display: Disable video window (always True in headless env)
        no_tts: Disable TTS alerts
    """
    source = video_source if video_source is not None else CONFIG["video"]["source"]

    print("=" * 70)
    print("🛡️  PPE Safety Detection System v2.0 — Bilingual")
    print("=" * 70)
    print(f"   👤 User ID: {user_id}")
    print(f"   📹 Source: {source}")

    # Load model
    model_path = os.path.join(os.path.dirname(__file__), "..", CONFIG["model"]["weights_path"])
    model_path = os.path.abspath(model_path)
    if not os.path.exists(model_path):
        print(f"❌ Model not found: {model_path}")
        return
    print(f"📦 Loading model: {model_path}")
    model = YOLO(model_path)

    # Setup components
    zone_engine = ZoneEngine(CONFIG["zones"])
    violation_tracker = ViolationTracker(
        cooldown_seconds=CONFIG["alerts"]["cooldown_seconds"],
        min_frames=CONFIG["alerts"]["min_frames_for_alert"],
    )

    # TTS engine — always bilingual (both)
    tts_engine = None
    if CONFIG["alerts"]["tts_enabled"] and not no_tts:
        tts_engine = TTSEngine(language="both", enabled=True)

    # Open video
    print(f"🎥 Opening video source: {source}")
    if isinstance(source, str) and not os.path.exists(source):
        print(f"❌ Video file not found: {source}")
        return

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"❌ Cannot open video source: {source}")
        return

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    is_live = isinstance(source, int) or str(source).isdigit()

    print(f"   Resolution: {frame_w}x{frame_h} @ {fps} FPS")
    if total_frames > 0:
        duration_s = total_frames / fps
        print(f"   Total frames: {total_frames} ({duration_s:.1f}s / {duration_s/60:.1f}min)")

    # Setup output video writer
    output_dir = os.path.join(os.path.dirname(__file__), "..", CONFIG["video"]["output_dir"])
    os.makedirs(output_dir, exist_ok=True)
    snapshot_dir = os.path.join(os.path.dirname(__file__), "..", CONFIG["alerts"]["snapshot_dir"])
    os.makedirs(snapshot_dir, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"ppe_detection_{user_id}_{timestamp_str}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_writer = cv2.VideoWriter(output_path, fourcc, fps, (frame_w, frame_h))

    # Class info
    class_names = CONFIG["classes"]["names"]
    violation_ids_set = set(CONFIG["classes"]["violation_ids"])
    COLORS = {
        "ppe": (0, 200, 0),
        "violation": (0, 0, 255),
        "person": (255, 180, 0),
    }

    # Stats
    stats = {
        "total_violations": 0,
        "alerts_fired": 0,
        "frames_processed": 0,
        "worker_ids": set(),
    }

    # Register session for working hours
    session_id = start_session(user_id, source, is_live=is_live)
    session_start_time = datetime.now()

    print(f"\n🚀 Starting detection... (no display — headless mode)\n")

    frame_count = 0
    fps_timer = time.time()
    fps_actual = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            stats["frames_processed"] = frame_count

            # Calculate real FPS
            if frame_count % 30 == 0:
                now = time.time()
                fps_actual = 30.0 / max(0.001, now - fps_timer)
                fps_timer = now

            # Run YOLO detection with tracking
            results = model.track(
                frame,
                persist=True,
                conf=CONFIG["model"]["confidence_threshold"],
                iou=CONFIG["model"]["iou_threshold"],
                imgsz=CONFIG["model"]["image_size"],
                verbose=False,
                tracker=CONFIG["tracking"]["tracker"],
            )

            # Draw zones
            draw_zones(frame, zone_engine)

            # Process detections
            if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                boxes = results[0].boxes
                person_violations = defaultdict(list)
                person_bboxes = {}

                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i])
                    conf = float(boxes.conf[i])
                    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                    track_id = int(boxes.id[i]) if boxes.id is not None else -1

                    cls_name = (class_names.get(cls_id, f"class_{cls_id}")
                                if isinstance(class_names, dict) else class_names[cls_id])
                    is_violation = cls_id in violation_ids_set

                    color = COLORS["violation"] if is_violation else COLORS["ppe"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    label = f"{cls_name} {conf:.2f}"
                    if track_id >= 0:
                        label = f"ID:{track_id} {label}"
                        stats["worker_ids"].add(track_id)

                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
                    cv2.putText(frame, label, (x1 + 2, y1 - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                    if is_violation and track_id >= 0:
                        person_violations[track_id].append(cls_id)
                        cx = (x1 + x2) // 2
                        cy = (y1 + y2) // 2
                        person_bboxes[track_id] = (cx, cy, x1, y1, x2, y2)

                # Check violations in zones
                for track_id, viol_ids in person_violations.items():
                    if track_id not in person_bboxes:
                        continue

                    cx, cy, x1, y1, x2, y2 = person_bboxes[track_id]
                    zone = zone_engine.check_person_in_zone((cx, cy), frame_w, frame_h)
                    zone_name = zone["name"] if zone else "Open Area"

                    violation_tracker.update(track_id, viol_ids)
                    should_alert, confirmed_violations = violation_tracker.should_alert(track_id)

                    if should_alert:
                        stats["total_violations"] += 1
                        stats["alerts_fired"] += 1

                        # Build bilingual alert
                        alert = build_alert(track_id, confirmed_violations, zone_name)

                        if alert:
                            print(f"\n{'='*60}")
                            print(f"🚨 VIOLATION #{stats['total_violations']} @ Frame {frame_count}")
                            print(f"   [EN] {alert['text_en']}")
                            print(f"   [AR] {alert['text_ar']}")
                            print(f"   Severity: {alert['severity'].upper()}")
                            print(f"   Time: {alert['timestamp']}")
                            print(f"{'='*60}")

                            # Bilingual TTS — Arabic first, then English
                            if tts_engine:
                                tts_en, tts_ar = build_tts_texts(
                                    track_id, confirmed_violations, zone_name
                                )
                                tts_engine.speak(
                                    text_en=tts_en,
                                    text_ar=tts_ar,
                                    blocking=False  # non-blocking so detection continues
                                )

                            # Save snapshot
                            snap_path = None
                            if CONFIG["alerts"]["save_snapshots"]:
                                snap_name = f"violation_{stats['total_violations']}_{user_id}_{timestamp_str}.jpg"
                                snap_path = os.path.join(snapshot_dir, snap_name)
                                # Draw red border on snapshot
                                snap_frame = frame.copy()
                                cv2.rectangle(snap_frame, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 4)
                                cv2.putText(snap_frame, "VIOLATION", (x1, y2 + 25),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                                cv2.imwrite(snap_path, snap_frame)
                                print(f"   📸 Snapshot: {snap_path}")

                            # Log to backend with user_id
                            log_violation_to_backend(alert, snap_path, user_id=user_id)

                            # Draw alert overlay on frame
                            cv2.rectangle(frame, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (0, 0, 255), 4)
                            cv2.putText(frame, "VIOLATION", (x1, y2 + 25),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Draw HUD with real timestamp and user info
            draw_hud(frame, frame_count, total_frames, stats, fps_actual, user_id)

            # Write output frame
            out_writer.write(frame)

            # Progress indicator every 100 frames
            if frame_count % 100 == 0:
                elapsed = (datetime.now() - session_start_time).total_seconds()
                elapsed_str = f"{int(elapsed//60)}m {int(elapsed%60)}s"
                if total_frames > 0:
                    pct = frame_count / total_frames * 100
                    print(f"   📹 Frame {frame_count}/{total_frames} ({pct:.1f}%) | "
                          f"Elapsed: {elapsed_str} | Violations: {stats['total_violations']}")
                else:
                    print(f"   📹 Frame {frame_count} | Elapsed: {elapsed_str} | "
                          f"Violations: {stats['total_violations']}")

    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user")

    finally:
        # Cleanup
        cap.release()
        out_writer.release()
        if tts_engine:
            tts_engine.stop()
            tts_engine.cleanup()

        # End session — log working hours
        end_session(session_id, frame_count, stats["total_violations"])

        # Calculate real run time
        total_runtime = (datetime.now() - session_start_time).total_seconds()

    # ─── Final Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"📊 Detection Summary")
    print(f"{'='*60}")
    print(f"   User ID:          {user_id}")
    print(f"   Frames processed: {stats['frames_processed']}")
    print(f"   Workers detected: {len(stats['worker_ids'])}")
    print(f"   Total violations: {stats['total_violations']}")
    print(f"   Alerts fired:     {stats['alerts_fired']}")
    print(f"   Run time:         {_format_duration(total_runtime)}")
    print(f"   Output video:     {output_path}")
    print(f"{'='*60}\n")


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PPE Safety Detection System v2.0")
    parser.add_argument("--source", "-s", type=str, default=None,
                        help="Video source (file path or camera index)")
    parser.add_argument("--user-id", "-u", type=str, default="operator_01",
                        help="User/operator ID for database logging")
    parser.add_argument("--no-display", action="store_true", default=True,
                        help="Disable video display window (default: headless)")
    parser.add_argument("--no-tts", action="store_true",
                        help="Disable TTS alerts")
    args = parser.parse_args()

    # Always run headless (display not supported without GTK)
    CONFIG["video"]["show_display"] = False

    source = args.source
    if source and source.isdigit():
        source = int(source)

    run_detection(
        video_source=source,
        user_id=args.user_id,
        no_display=True,
        no_tts=args.no_tts,
    )
