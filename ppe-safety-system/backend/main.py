"""
FastAPI Backend v2.1 — PPE Safety System
Adds: MJPEG live stream, detection control endpoints, deduction fix
"""
import os, sqlite3, threading, time as _time, json
from datetime import datetime, timedelta
from contextlib import contextmanager
from collections import defaultdict

import yaml, cv2, numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

DB_PATH    = os.path.join(os.path.dirname(__file__), "..", CONFIG["backend"]["database"])
SCHEMA_PATH= os.path.join(os.path.dirname(__file__), "schema.sql")

def init_db():
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    for col, defval in [("user_id","TEXT NOT NULL DEFAULT 'unknown'"),
                        ("deduction","INTEGER DEFAULT 0"),
                        ("deduction_amount","REAL DEFAULT 0.0")]:
        try: conn.execute(f"ALTER TABLE violations ADD COLUMN {col} {defval}")
        except: pass
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS detection_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'system',
            source TEXT NOT NULL DEFAULT 'unknown',
            started_at TEXT NOT NULL,
            ended_at TEXT DEFAULT NULL,
            total_frames INTEGER DEFAULT 0,
            violations_detected INTEGER DEFAULT 0,
            is_live INTEGER DEFAULT 0)""")
    except: pass
    conn.commit(); conn.close()
    print(f"✅ Database initialized: {DB_PATH}")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try: yield conn
    finally: conn.close()

init_db()

# ── Detection State ─────────────────────────────────────────────────────────
_det = {
    "running": False, "source": None, "user_id": "operator",
    "stats": {"violations": 0, "frames": 0, "workers": 0, "fps": 0.0,
              "total_frames": 0, "progress": 0.0},
    "session_id": None, "started_at": None, "error": None,
}
_frame_jpg = [None]           # latest JPEG bytes
_frame_lock = threading.Lock()
_stop_event = threading.Event()
_det_thread = None

# ── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(title="PPE Safety API", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard")
SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "..", "snapshots")
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

if os.path.exists(os.path.join(DASHBOARD_DIR, "static")):
    app.mount("/static", StaticFiles(directory=os.path.join(DASHBOARD_DIR,"static")), name="static")
app.mount("/snapshots", StaticFiles(directory=SNAPSHOTS_DIR), name="snapshots")

# ── Pydantic Models ─────────────────────────────────────────────────────────
class ViolationCreate(BaseModel):
    user_id: str = "unknown"; track_id: int; zone: str = "Unknown"
    severity: str = "single"; missing_items: str; alert_text: str
    timestamp: str; snapshot_path: str = ""

class ViolationUpdate(BaseModel):
    resolved: Optional[int]=None; notes: Optional[str]=None
    deduction: Optional[int]=None; deduction_amount: Optional[float]=None

class SessionCreate(BaseModel):
    user_id: str="system"; source: str="unknown"; started_at: str; is_live: int=0

class SessionEnd(BaseModel):
    ended_at: str; total_frames: int=0; violations_detected: int=0

class DetectionStart(BaseModel):
    source: str="0"; user_id: str="operator_01"; no_tts: bool=False

# ── Helpers ──────────────────────────────────────────────────────────────────
def _fmt(sec):
    sec=int(sec); h=sec//3600; m=(sec%3600)//60; s=sec%60
    return f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")

# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    p = os.path.join(DASHBOARD_DIR,"index.html")
    return HTMLResponse(open(p,encoding="utf-8").read() if os.path.exists(p) else "<h1>Not found</h1>")

# ── Violations ───────────────────────────────────────────────────────────────
@app.post("/api/violations")
async def create_violation(v: ViolationCreate):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO violations (user_id,track_id,zone,severity,missing_items,alert_text,timestamp,snapshot_path) VALUES (?,?,?,?,?,?,?,?)",
            (v.user_id,v.track_id,v.zone,v.severity,v.missing_items,v.alert_text,v.timestamp,v.snapshot_path))
        conn.commit()
    return {"status":"ok","id":cur.lastrowid}

@app.get("/api/violations")
async def get_violations(limit:int=Query(50,ge=1,le=500), offset:int=Query(0,ge=0),
    severity:Optional[str]=None, zone:Optional[str]=None, resolved:Optional[int]=None,
    user_id:Optional[str]=None, date_from:Optional[str]=None, date_to:Optional[str]=None):
    q="SELECT * FROM violations WHERE 1=1"; p=[]
    if severity: q+=" AND severity=?"; p.append(severity)
    if zone:     q+=" AND zone=?";     p.append(zone)
    if resolved is not None: q+=" AND resolved=?"; p.append(resolved)
    if user_id:  q+=" AND user_id=?";  p.append(user_id)
    if date_from:q+=" AND timestamp>=?";p.append(date_from)
    if date_to:  q+=" AND timestamp<=?";p.append(date_to)
    cq=q.replace("SELECT *","SELECT COUNT(*)")
    q+=" ORDER BY id DESC LIMIT ? OFFSET ?"; p.extend([limit,offset])
    with get_db() as conn:
        rows=conn.execute(q,p).fetchall()
        total=conn.execute(cq,p[:-2]).fetchone()[0]
    return {"violations":[dict(r) for r in rows],"total":total}

@app.get("/api/violations/{vid}")
async def get_violation(vid:int):
    with get_db() as conn:
        row=conn.execute("SELECT * FROM violations WHERE id=?",(vid,)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    return dict(row)

@app.put("/api/violations/{vid}")
async def update_violation(vid:int, u:ViolationUpdate):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM violations WHERE id=?",(vid,)).fetchone():
            raise HTTPException(404,"Not found")
        if u.resolved is not None:
            ra=datetime.now().isoformat() if u.resolved else None
            conn.execute("UPDATE violations SET resolved=?,resolved_at=? WHERE id=?",(u.resolved,ra,vid))
        if u.notes is not None:
            conn.execute("UPDATE violations SET notes=? WHERE id=?",(u.notes,vid))
        if u.deduction is not None:
            conn.execute("UPDATE violations SET deduction=? WHERE id=?",(u.deduction,vid))
        if u.deduction_amount is not None:
            conn.execute("UPDATE violations SET deduction_amount=? WHERE id=?",(u.deduction_amount,vid))
        conn.commit()
    return {"status":"ok"}

@app.delete("/api/violations/{vid}")
async def delete_violation(vid:int):
    with get_db() as conn:
        conn.execute("DELETE FROM violations WHERE id=?",(vid,)); conn.commit()
    return {"status":"ok"}

# ── Sessions ─────────────────────────────────────────────────────────────────
@app.post("/api/sessions")
async def create_session(s:SessionCreate):
    with get_db() as conn:
        cur=conn.execute("INSERT INTO detection_sessions (user_id,source,started_at,is_live) VALUES (?,?,?,?)",
            (s.user_id,s.source,s.started_at,s.is_live)); conn.commit()
    return {"status":"ok","session_id":cur.lastrowid}

@app.put("/api/sessions/{sid}")
async def end_session(sid:int, d:SessionEnd):
    with get_db() as conn:
        conn.execute("UPDATE detection_sessions SET ended_at=?,total_frames=?,violations_detected=? WHERE id=?",
            (d.ended_at,d.total_frames,d.violations_detected,sid)); conn.commit()
    return {"status":"ok"}

@app.get("/api/sessions")
async def get_sessions(user_id:Optional[str]=None, limit:int=Query(50,ge=1,le=200)):
    q="SELECT * FROM detection_sessions WHERE 1=1"; p=[]
    if user_id: q+=" AND user_id=?"; p.append(user_id)
    q+=" ORDER BY id DESC LIMIT ?"; p.append(limit)
    with get_db() as conn:
        rows=conn.execute(q,p).fetchall()
    sessions=[]
    for r in rows:
        s=dict(r)
        if s.get("started_at") and s.get("ended_at"):
            try:
                dur=(datetime.fromisoformat(s["ended_at"])-datetime.fromisoformat(s["started_at"])).total_seconds()
                s["duration_seconds"]=max(0,dur); s["duration_formatted"]=_fmt(max(0,dur))
            except: s["duration_seconds"]=0; s["duration_formatted"]="—"
        else: s["duration_seconds"]=0; s["duration_formatted"]="In Progress"
        sessions.append(s)
    return {"sessions":sessions}

@app.get("/api/working-hours")
async def working_hours():
    today=datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows=conn.execute("SELECT started_at,ended_at FROM detection_sessions WHERE ended_at IS NOT NULL").fetchall()
    tot=0; tod=0
    for r in rows:
        try:
            dur=max(0,(datetime.fromisoformat(r["ended_at"])-datetime.fromisoformat(r["started_at"])).total_seconds())
            tot+=dur
            if r["started_at"].startswith(today): tod+=dur
        except: pass
    return {"total_seconds":tot,"total_formatted":_fmt(tot),"total_hours":round(tot/3600,2),
            "today_seconds":tod,"today_formatted":_fmt(tod),"today_hours":round(tod/3600,2)}

# ── Stats ────────────────────────────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    today=datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        sr=conn.execute("SELECT * FROM violation_stats").fetchone()
        stats=dict(sr) if sr else {}
        today_c=conn.execute("SELECT COUNT(*) FROM violations WHERE timestamp LIKE ?",(f"{today}%",)).fetchone()[0]
        hr_ago=(datetime.now()-timedelta(hours=1)).isoformat()
        hr_c=conn.execute("SELECT COUNT(*) FROM violations WHERE timestamp>=?",(hr_ago,)).fetchone()[0]
        sev=conn.execute("SELECT severity,COUNT(*) as count FROM violations GROUP BY severity").fetchall()
        zone=conn.execute("SELECT zone,COUNT(*) as count FROM violations GROUP BY zone ORDER BY count DESC LIMIT 10").fetchall()
        items=conn.execute("SELECT missing_items,COUNT(*) as count FROM violations GROUP BY missing_items ORDER BY count DESC LIMIT 10").fetchall()
        recent=conn.execute("SELECT * FROM violations ORDER BY id DESC LIMIT 10").fetchall()
        # Deductions — explicit query always fresh
        ded_c=conn.execute("SELECT COUNT(*) FROM violations WHERE deduction=1").fetchone()[0]
        ded_amt=conn.execute("SELECT COALESCE(SUM(deduction_amount),0) FROM violations WHERE deduction=1").fetchone()[0]
        # Hourly
        hourly=[]
        for i in range(24):
            hs=(datetime.now()-timedelta(hours=23-i)).replace(minute=0,second=0,microsecond=0)
            he=hs+timedelta(hours=1)
            c=conn.execute("SELECT COUNT(*) FROM violations WHERE timestamp>=? AND timestamp<?",(hs.isoformat(),he.isoformat())).fetchone()[0]
            hourly.append({"hour":hs.strftime("%H:00"),"count":c})
        # Working hours
        sess=conn.execute("SELECT started_at,ended_at FROM detection_sessions WHERE ended_at IS NOT NULL").fetchall()
        tot_s=0; tod_s=0
        for r in sess:
            try:
                dur=max(0,(datetime.fromisoformat(r["ended_at"])-datetime.fromisoformat(r["started_at"])).total_seconds())
                tot_s+=dur
                if r["started_at"].startswith(today): tod_s+=dur
            except: pass
    return {
        "overview":{**stats,"today_count":today_c,"last_hour_count":hr_c,
                    "deduction_count":ded_c,"total_deductions":round(ded_amt,2),
                    "working_hours_today":round(tod_s/3600,2),"working_hours_total":round(tot_s/3600,2),
                    "working_hours_today_formatted":_fmt(tod_s),"working_hours_total_formatted":_fmt(tot_s)},
        "severity_breakdown":[dict(r) for r in sev],
        "zone_breakdown":[dict(r) for r in zone],
        "hourly_trend":hourly,
        "top_violations":[dict(r) for r in items],
        "recent_violations":[dict(r) for r in recent],
    }

@app.get("/api/stats/live")
async def live_stats():
    today=datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        total=conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        unres=conn.execute("SELECT COUNT(*) FROM violations WHERE resolved=0").fetchone()[0]
        ded_c=conn.execute("SELECT COUNT(*) FROM violations WHERE deduction=1").fetchone()[0]
        five_ago=(datetime.now()-timedelta(minutes=5)).isoformat()
        rec5=conn.execute("SELECT COUNT(*) FROM violations WHERE timestamp>=?",(five_ago,)).fetchone()[0]
        latest=conn.execute("SELECT * FROM violations ORDER BY id DESC LIMIT 1").fetchone()
        sess=conn.execute("SELECT started_at,ended_at FROM detection_sessions WHERE ended_at IS NOT NULL AND started_at LIKE ?",(f"{today}%",)).fetchall()
    tod_s=0
    for r in sess:
        try: tod_s+=max(0,(datetime.fromisoformat(r["ended_at"])-datetime.fromisoformat(r["started_at"])).total_seconds())
        except: pass
    return {"total_violations":total,"unresolved":unres,"deduction_count":ded_c,
            "recent_5min":rec5,"latest":dict(latest) if latest else None,
            "working_hours_today_formatted":_fmt(tod_s),
            "detection_running":_det["running"],"detection_stats":_det["stats"]}

# ── Detection Control ─────────────────────────────────────────────────────────
@app.post("/api/detection/start")
async def start_detection(req: DetectionStart):
    global _det_thread
    if _det["running"]:
        return {"status":"already_running","stats":_det["stats"]}
    _stop_event.clear()
    _det_thread = threading.Thread(target=_run_det, args=(req.source, req.user_id, req.no_tts), daemon=True)
    _det_thread.start()
    return {"status":"started"}

@app.post("/api/detection/stop")
async def stop_detection():
    _stop_event.set()
    _det["running"] = False
    return {"status":"stopped"}

@app.get("/api/detection/status")
async def detection_status():
    s = dict(_det)
    s["stats"] = {**s["stats"], "workers": s["stats"].get("workers", 0)
                  if isinstance(s["stats"].get("workers"), int)
                  else len(s["stats"].get("workers", set()))}
    return s

# ── MJPEG Stream ──────────────────────────────────────────────────────────────
@app.get("/api/stream")
async def video_stream():
    def gen():
        while True:
            with _frame_lock:
                jpg = _frame_jpg[0]
            if jpg:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n'
            else:
                # placeholder black frame
                blank = np.zeros((360,640,3), np.uint8)
                cv2.putText(blank,"🎥  Start detection to see live feed",(60,180),
                            cv2.FONT_HERSHEY_SIMPLEX,0.75,(80,80,80),2)
                _,buf = cv2.imencode('.jpg', blank)
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
            _time.sleep(0.04)
    return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')

# ── Background Detection Thread ───────────────────────────────────────────────
def _run_det(source: str, user_id: str, no_tts: bool):
    global _frame_jpg, _det
    _det.update(running=True, source=source, user_id=user_id, error=None,
                started_at=datetime.now().isoformat(),
                stats={"violations":0,"frames":0,"workers":set(),"fps":0.0,"total_frames":0,"progress":0.0})
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from ultralytics import YOLO
        from alerts.alert_builder import build_alert, build_tts_texts
        from alerts.tts import TTSEngine

        cfg = CONFIG
        mp = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", cfg["model"]["weights_path"]))
        model = YOLO(mp)

        tts = None
        if cfg["alerts"]["tts_enabled"] and not no_tts:
            try: tts = TTSEngine(language="both", enabled=True)
            except: pass

        src = source
        try: src = int(source)
        except ValueError: pass

        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            _det["error"] = f"Cannot open: {source}"; _det["running"] = False; return

        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        native_fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
        total_fr   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        is_live    = isinstance(src, int)
        _det["stats"]["total_frames"] = total_fr

        # Session
        sid = None
        with get_db() as conn:
            cur=conn.execute("INSERT INTO detection_sessions (user_id,source,started_at,is_live) VALUES (?,?,?,?)",
                (user_id,str(source),datetime.now().isoformat(),1 if is_live else 0)); conn.commit(); sid=cur.lastrowid
        _det["session_id"] = sid

        snap_dir = os.path.join(os.path.dirname(__file__), "..", "snapshots")
        os.makedirs(snap_dir, exist_ok=True)
        cls_names   = cfg["classes"]["names"]
        viol_ids    = set(cfg["classes"]["violation_ids"])
        zones_cfg   = cfg["zones"]
        cooldown    = cfg["alerts"]["cooldown_seconds"]
        min_fr      = cfg["alerts"]["min_frames_for_alert"]
        save_snaps  = cfg["alerts"]["save_snapshots"]
        ts_str      = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Zone polygons
        zone_polys = [{"name":z["name"],"polygon":np.array(z["polygon"],np.float32),"color":tuple(z["color"])} for z in zones_cfg]

        viol_cool = defaultdict(float)
        viol_frames = defaultdict(lambda: defaultdict(int))
        frame_count = 0
        fps_timer   = _time.time()

        while not _stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                if not is_live: break
                _time.sleep(0.01); continue

            frame_count += 1
            _det["stats"]["frames"] = frame_count
            if total_fr > 0:
                _det["stats"]["progress"] = round(frame_count / total_fr * 100, 1)
            if frame_count % 30 == 0:
                n = _time.time()
                _det["stats"]["fps"] = round(30/max(0.001,n-fps_timer),1); fps_timer=n

            results = model.track(frame, persist=True,
                conf=cfg["model"]["confidence_threshold"],
                iou=cfg["model"]["iou_threshold"],
                imgsz=cfg["model"]["image_size"],
                verbose=False, tracker=cfg["tracking"]["tracker"])

            # Draw zones
            for z in zone_polys:
                poly=z["polygon"].copy(); poly[:,0]*=fw; poly[:,1]*=fh; poly=poly.astype(np.int32)
                ov=frame.copy(); cv2.fillPoly(ov,[poly],z["color"])
                cv2.addWeighted(ov,0.1,frame,0.9,0,frame)
                cv2.polylines(frame,[poly],True,z["color"],2)
                cv2.putText(frame,z["name"],(poly[0][0]+5,poly[0][1]+22),cv2.FONT_HERSHEY_SIMPLEX,0.6,z["color"],2)

            if results and results[0].boxes is not None and len(results[0].boxes)>0:
                boxes=results[0].boxes
                pv=defaultdict(list); pb={}
                for i in range(len(boxes)):
                    ci=int(boxes.cls[i]); cf=float(boxes.conf[i])
                    x1,y1,x2,y2=boxes.xyxy[i].cpu().numpy().astype(int)
                    tid=int(boxes.id[i]) if boxes.id is not None else -1
                    cn=(cls_names.get(ci,f"c{ci}") if isinstance(cls_names,dict) else cls_names[ci])
                    iv=ci in viol_ids
                    col=(0,0,255) if iv else (0,200,0)
                    cv2.rectangle(frame,(x1,y1),(x2,y2),col,2)
                    lbl=f"{'ID:'+str(tid)+' ' if tid>=0 else ''}{cn} {cf:.2f}"
                    (tw,th),_=cv2.getTextSize(lbl,cv2.FONT_HERSHEY_SIMPLEX,0.45,1)
                    cv2.rectangle(frame,(x1,y1-th-6),(x1+tw+4,y1),col,-1)
                    cv2.putText(frame,lbl,(x1+2,y1-3),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
                    if tid>=0:
                        _det["stats"]["workers"].add(tid)
                        if iv: pv[tid].append(ci); pb[tid]=(x1,y1,x2,y2)

                for tid,vids in pv.items():
                    for vid in vids: viol_frames[tid][vid]+=1
                    now=_time.time()
                    if now-viol_cool[tid]>=cooldown:
                        conf_vids=[v for v,c in viol_frames[tid].items() if c>=min_fr]
                        if conf_vids:
                            viol_cool[tid]=now
                            for v in conf_vids: viol_frames[tid][v]=0
                            alert=build_alert(tid,conf_vids,"Construction Zone A")
                            if alert:
                                _det["stats"]["violations"]+=1
                                if tts:
                                    ten,tar=build_tts_texts(tid,conf_vids,"Construction Zone A")
                                    tts.speak(text_en=ten,text_ar=tar,blocking=False)
                                snap_path=""
                                if save_snaps and tid in pb:
                                    x1,y1,x2,y2=pb[tid]
                                    sn=frame.copy()
                                    cv2.rectangle(sn,(x1-3,y1-3),(x2+3,y2+3),(0,0,255),4)
                                    cv2.putText(sn,"VIOLATION",(x1,y2+25),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),2)
                                    fname=f"violation_{_det['stats']['violations']}_{user_id}_{ts_str}.jpg"
                                    fpath=os.path.join(snap_dir,fname)
                                    cv2.imwrite(fpath,sn); snap_path=fname
                                with get_db() as conn:
                                    conn.execute(
                                        "INSERT INTO violations (user_id,track_id,zone,severity,missing_items,alert_text,timestamp,snapshot_path) VALUES (?,?,?,?,?,?,?,?)",
                                        (user_id,tid,alert["zone"],alert["severity"],
                                         ", ".join(alert["missing_items"]),alert["text_en"],
                                         alert["timestamp"],snap_path)); conn.commit()

            # HUD overlay
            now_s=datetime.now().strftime("%H:%M:%S")
            wc=len(_det["stats"]["workers"]) if isinstance(_det["stats"]["workers"],set) else _det["stats"]["workers"]
            cv2.rectangle(frame,(0,0),(fw,48),(10,10,30),-1)
            cv2.putText(frame,f"PPE Monitor | {now_s} | User: {user_id} | FPS: {_det['stats']['fps']:.0f}",
                        (8,18),cv2.FONT_HERSHEY_SIMPLEX,0.52,(0,255,255),1)
            prog=""
            if total_fr>0: prog=f" | {_det['stats']['progress']:.1f}%"
            cv2.putText(frame,f"Frame: {frame_count}{prog} | Violations: {_det['stats']['violations']} | Workers: {wc}",
                        (8,40),cv2.FONT_HERSHEY_SIMPLEX,0.46,(200,200,200),1)

            # Push to stream buffer
            _,buf=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,75])
            with _frame_lock:
                _frame_jpg[0]=buf.tobytes()

        cap.release()
        if tts: tts.stop(); tts.cleanup()

    except Exception as e:
        _det["error"]=str(e); print(f"❌ Detection error: {e}")
    finally:
        _det["running"]=False
        workers_set=_det["stats"].get("workers",set())
        _det["stats"]["workers"]=len(workers_set) if isinstance(workers_set,set) else workers_set
        with _frame_lock: _frame_jpg[0]=None
        if _det.get("session_id"):
            with get_db() as conn:
                conn.execute("UPDATE detection_sessions SET ended_at=?,total_frames=?,violations_detected=? WHERE id=?",
                    (datetime.now().isoformat(),_det["stats"]["frames"],_det["stats"]["violations"],_det["session_id"]))
                conn.commit()

if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app",host=CONFIG["backend"]["host"],port=CONFIG["backend"]["port"],reload=False)
