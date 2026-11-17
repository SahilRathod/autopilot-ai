"""V0.5 local media intelligence: metadata, scene-boundary suggestions, and safe review.

Scene changes are only *candidate edit points*, not semantic gameplay highlights.
No network access, uploads, ML downloads, or automatic publishing.
"""
import hashlib
import json
import math
import re
import shutil
import subprocess
from fractions import Fraction

from app import editor, media_pipeline, platform_core as core

# Bounded CPU work: 2 fps at 160 px, at most ten minutes per scan.
MAX_SCAN_SECONDS = 600.0
MAX_FILE_BYTES = 20 * 1024 ** 3
SHOWINFO_TIME = re.compile(r"\bpts_time:([0-9]+(?:\.[0-9]+)?)")


def initialize():
    with core.connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS media_assets (
            id INTEGER PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            file_bytes INTEGER NOT NULL,
            duration_seconds REAL NOT NULL CHECK(duration_seconds > 0),
            width INTEGER NOT NULL CHECK(width > 0),
            height INTEGER NOT NULL CHECK(height > 0),
            fps REAL NOT NULL CHECK(fps > 0),
            video_codec TEXT NOT NULL,
            audio_codec TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, channel_id, filename, sha256)
        );
        CREATE INDEX IF NOT EXISTS idx_media_assets_scope
            ON media_assets(workspace_id, channel_id, id DESC);
        CREATE TABLE IF NOT EXISTS media_candidates (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            start_seconds REAL NOT NULL CHECK(start_seconds >= 0),
            duration_seconds REAL NOT NULL CHECK(duration_seconds > 0),
            reason TEXT NOT NULL CHECK(reason IN ('opening_segment', 'scene_change')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_media_candidates_scope
            ON media_candidates(workspace_id, channel_id, asset_id, id);
        """)


def _channel(workspace_id, channel_id):
    with core.connect() as db:
        if db.execute("SELECT 1 FROM channels WHERE workspace_id=? AND id=?",
                      (workspace_id, channel_id)).fetchone() is None:
            raise ValueError("Channel not found in this workspace")


def _source(filename):
    if not isinstance(filename, str) or not filename:
        raise ValueError("Source filename required")
    return editor.source(filename)


def _fingerprint(path):
    size = path.stat().st_size
    if size <= 0 or size > MAX_FILE_BYTES:
        raise ValueError("Media file must be nonempty and at most 20 GiB")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return size, digest.hexdigest()


def _positive_number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label} reported by ffprobe") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Invalid {label} reported by ffprobe")
    return number


def probe_metadata(path):
    """Inspect video metadata via a bounded local ffprobe subprocess."""
    if not shutil.which("ffprobe"):
        raise RuntimeError("FFprobe is required (install FFmpeg and add it to PATH)")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video = next(s for s in streams if s.get("codec_type") == "video")
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = _positive_number(data.get("format", {}).get("duration"), "duration")
        fps = float(Fraction(video.get("avg_frame_rate", "0/1")))
        return {
            "duration_seconds": duration,
            "width": int(_positive_number(video.get("width"), "width")),
            "height": int(_positive_number(video.get("height"), "height")),
            "fps": _positive_number(fps, "frame rate"),
            "video_codec": str(video.get("codec_name") or "unknown")[:60],
            "audio_codec": str(audio.get("codec_name") or "unknown")[:60] if audio else None,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("FFprobe could not inspect this media file") from exc
    except (ValueError, KeyError, StopIteration, TypeError, ZeroDivisionError, json.JSONDecodeError) as exc:
        raise ValueError("Media does not contain valid video metadata") from exc


def _asset_record(row):
    return dict(row)


def import_media(workspace_id, channel_id, filename):
    """Register original media without copying or modifying it."""
    initialize()
    _channel(workspace_id, channel_id)
    source = _source(filename)
    size, digest = _fingerprint(source)
    with core.connect() as db:
        found = db.execute("""
            SELECT * FROM media_assets
            WHERE workspace_id=? AND channel_id=? AND filename=? AND sha256=?
        """, (workspace_id, channel_id, filename, digest)).fetchone()
        if found:
            return _asset_record(found)
    metadata = probe_metadata(source)
    # Reject a source changed while ffprobe was running.
    if (size, digest) != _fingerprint(source):
        raise ValueError("Source changed during import; retry")
    with core.connect() as db:
        db.execute("""INSERT OR IGNORE INTO media_assets
            (workspace_id,channel_id,filename,sha256,file_bytes,duration_seconds,
             width,height,fps,video_codec,audio_codec)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (workspace_id, channel_id, filename, digest, size,
             metadata["duration_seconds"], metadata["width"], metadata["height"],
             metadata["fps"], metadata["video_codec"], metadata["audio_codec"]))
        row = db.execute("""
            SELECT * FROM media_assets
            WHERE workspace_id=? AND channel_id=? AND filename=? AND sha256=?
        """, (workspace_id, channel_id, filename, digest)).fetchone()
        db.execute("""INSERT INTO audit_log(workspace_id,channel_id,action,detail)
                      VALUES(?,?,?,?)""",
                   (workspace_id, channel_id, "media_imported", str(row["id"])))
        return _asset_record(row)


def assets(workspace_id, channel_id):
    initialize()
    _channel(workspace_id, channel_id)
    with core.connect() as db:
        return [dict(row) for row in db.execute("""
            SELECT * FROM media_assets WHERE workspace_id=? AND channel_id=?
            ORDER BY id DESC LIMIT 100
        """, (workspace_id, channel_id))]


def asset(workspace_id, channel_id, asset_id):
    initialize()
    _channel(workspace_id, channel_id)
    with core.connect() as db:
        row = db.execute("""
            SELECT * FROM media_assets WHERE workspace_id=? AND channel_id=? AND id=?
        """, (workspace_id, channel_id, asset_id)).fetchone()
        if row is None:
            raise ValueError("Media asset not found in this channel")
        return dict(row)


def _validated_source(record):
    source = _source(record["filename"])
    size, digest = _fingerprint(source)
    if size != record["file_bytes"] or digest != record["sha256"]:
        raise ValueError("Imported source has changed; import it again")
    return source


def detect_changes(source, scan_seconds, threshold):
    """Find approximate visual scene boundaries, not noteworthy game events."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required (install it and add it to PATH)")
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
        "-t", str(scan_seconds), "-i", str(source),
        "-vf", f"fps=2,scale=160:-2,select='gt(scene,{threshold})',showinfo",
        "-an", "-sn", "-dn", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                check=True, timeout=min(180, 20 + scan_seconds))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("FFmpeg scene scan failed or timed out") from exc
    times = []
    for line in result.stderr.splitlines():
        if "showinfo" not in line:
            continue
        match = SHOWINFO_TIME.search(line)
        if match:
            value = float(match.group(1))
            if math.isfinite(value) and 0 <= value <= scan_seconds:
                times.append(value)
    return times[:250]


def candidates(workspace_id, channel_id, asset_id):
    asset(workspace_id, channel_id, asset_id)
    with core.connect() as db:
        return [dict(row) for row in db.execute("""
            SELECT * FROM media_candidates
            WHERE workspace_id=? AND channel_id=? AND asset_id=? ORDER BY id
        """, (workspace_id, channel_id, asset_id))]


def scan_media(workspace_id, channel_id, asset_id, clip_seconds=30,
               threshold=0.35, max_scan_seconds=120):
    record = asset(workspace_id, channel_id, asset_id)
    numbers = (clip_seconds, threshold, max_scan_seconds)
    if (not all(isinstance(n, (float, int)) and math.isfinite(n) for n in numbers)
            or not 0.05 <= threshold <= 0.95
            or not 1 <= clip_seconds <= 120
            or not 2 <= max_scan_seconds <= MAX_SCAN_SECONDS):
        raise ValueError("Invalid scan settings (clip 1–120s, threshold 0.05–0.95, scan 2–600s)")
    source = _validated_source(record)
    scanned = min(float(max_scan_seconds), record["duration_seconds"])
    duration = min(float(clip_seconds), record["duration_seconds"])
    detected = detect_changes(source, scanned, float(threshold))
    # Keep at most 8 suggestions and at least 3 seconds apart; don't return
    # accidental duplicates near the opening. Suggestions aren't ranked highlights.
    entries = [(0.0, duration, "opening_segment")]
    starts = [0.0]
    for change_at in detected:
        try:
            when = float(change_at)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(when) or when < 0 or when > scanned:
            continue
        start = max(0.0, min(record["duration_seconds"] - duration, when - 1.0))
        if all(abs(start - old) >= 3.0 for old in starts):
            starts.append(start)
            entries.append((round(start, 3), duration, "scene_change"))
        if len(entries) >= 8:
            break
    with core.connect() as db:
        # SQLite transaction ensures a scan replaces candidates atomically.
        db.execute("""DELETE FROM media_candidates
                      WHERE workspace_id=? AND channel_id=? AND asset_id=?""",
                   (workspace_id, channel_id, asset_id))
        db.executemany("""INSERT INTO media_candidates
            (asset_id,workspace_id,channel_id,start_seconds,duration_seconds,reason)
            VALUES(?,?,?,?,?,?)""",
            [(asset_id, workspace_id, channel_id, *entry) for entry in entries])
        db.execute("""INSERT INTO audit_log(workspace_id,channel_id,action,detail)
                      VALUES(?,?,?,?)""", (workspace_id, channel_id, "media_scanned", str(asset_id)))
    return {"asset_id": asset_id, "candidate_count": len(entries),
            "scanned_seconds": scanned, "candidate_kind": "visual_scene_boundaries"}


def render_candidate(workspace_id, channel_id, candidate_id, job_id):
    initialize()
    _channel(workspace_id, channel_id)
    with core.connect() as db:
        candidate = db.execute("""
            SELECT m.filename,m.sha256,m.file_bytes,c.start_seconds,c.duration_seconds
            FROM media_candidates c JOIN media_assets m ON c.asset_id=m.id
            WHERE c.id=? AND c.workspace_id=? AND c.channel_id=?
              AND m.workspace_id=? AND m.channel_id=?
        """, (candidate_id, workspace_id, channel_id, workspace_id, channel_id)).fetchone()
        job = db.execute("""SELECT id FROM production_jobs
                            WHERE id=? AND workspace_id=? AND channel_id=? AND state='approved'""",
                         (job_id, workspace_id, channel_id)).fetchone()
        if candidate is None:
            raise ValueError("Candidate not found in this channel")
        if job is None:
            raise ValueError("Job must be approved and belong to the candidate's channel")
    _validated_source(candidate)
    return media_pipeline.render_job(workspace_id, job_id, candidate["filename"],
                                     candidate["start_seconds"], candidate["duration_seconds"])
