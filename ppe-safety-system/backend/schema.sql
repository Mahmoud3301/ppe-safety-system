-- ═══════════════════════════════════════════════════════════════════════════
-- PPE Safety System - Database Schema (SQLite)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'unknown',
    track_id INTEGER NOT NULL,
    zone TEXT NOT NULL DEFAULT 'Unknown',
    severity TEXT NOT NULL DEFAULT 'single',
    missing_items TEXT NOT NULL,
    alert_text TEXT NOT NULL,
    snapshot_path TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT DEFAULT NULL,
    notes TEXT DEFAULT '',
    deduction INTEGER DEFAULT 0,
    deduction_amount REAL DEFAULT 0.0
);

-- Detection sessions table (tracks run times for working hours)
CREATE TABLE IF NOT EXISTS detection_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'system',
    source TEXT NOT NULL DEFAULT 'unknown',
    started_at TEXT NOT NULL,
    ended_at TEXT DEFAULT NULL,
    total_frames INTEGER DEFAULT 0,
    violations_detected INTEGER DEFAULT 0,
    is_live INTEGER DEFAULT 0
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_violations_timestamp ON violations(timestamp);
CREATE INDEX IF NOT EXISTS idx_violations_severity ON violations(severity);
CREATE INDEX IF NOT EXISTS idx_violations_zone ON violations(zone);
CREATE INDEX IF NOT EXISTS idx_violations_resolved ON violations(resolved);
CREATE INDEX IF NOT EXISTS idx_violations_user_id ON violations(user_id);
CREATE INDEX IF NOT EXISTS idx_violations_track_id ON violations(track_id);

-- Stats view
CREATE VIEW IF NOT EXISTS violation_stats AS
SELECT
    COUNT(*) as total_violations,
    COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count,
    COUNT(CASE WHEN severity = 'multiple' THEN 1 END) as multiple_count,
    COUNT(CASE WHEN severity = 'single' THEN 1 END) as single_count,
    COUNT(CASE WHEN resolved = 1 THEN 1 END) as resolved_count,
    COUNT(CASE WHEN resolved = 0 THEN 1 END) as unresolved_count,
    COUNT(DISTINCT track_id) as unique_workers,
    COUNT(DISTINCT zone) as zones_affected,
    COUNT(CASE WHEN deduction = 1 THEN 1 END) as deduction_count,
    COALESCE(SUM(deduction_amount), 0) as total_deductions
FROM violations;
