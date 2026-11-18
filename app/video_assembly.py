"""Offline V0.5-M4: assemble approved clips, audio handling, and user-authored subtitles.

Captions are timed text supplied by the creator, NOT speech transcription.
No cloud calls, automatic publishing, copyrighted music libraries, or new dependencies.
"""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from app import editor, media_intelligence as media, media_pipeline, platform_core as core

QUALITY = {
    "fast": {"short": (720, 1280), "long": (1280, 720), "preset": "veryfast", "crf": "25"},
    "high": {"short": (1080, 1920), "long": (1920, 1080), "preset": "medium", "crf": "21"},
}
AUDIO_MODES = frozenset(("preserve", "normalize", "mute"))
CAPTION_MODES = frozenset(("none", "soft", "burn"))
MAX_CLIPS = 8


def initialize():
    with core.connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS assembly_exports (
            job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id),
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            state TEXT NOT NULL CHECK(state IN ('rendering','ready')),
            candidate_ids_json TEXT NOT NULL,
            caption_lines_json TEXT NOT NULL,
            caption_mode TEXT NOT NULL,
            audio_mode TEXT NOT NULL,
            quality TEXT NOT NULL,
            output_path TEXT,
            total_seconds REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)


def _captions(lines, caption_mode, total):
    if caption_mode not in CAPTION_MODES:
        raise ValueError("Invalid caption mode")
    if not isinstance(lines, list) or len(lines) > 40:
        raise ValueError("Caption lines must be a list of at most 40 lines")
    clean = []
    for item in lines:
        if (not isinstance(item, str) or not 1 <= len(item.strip()) <= 160
                or any(ord(char) < 32 for char in item)
                or "<" in item or ">" in item):
            raise ValueError("Invalid caption line; use plain text without markup or newlines")
        clean.append(item.strip())
    if caption_mode == "none" and clean:
        raise ValueError("Choose soft or burn captions to use caption text")
    if caption_mode != "none" and not clean:
        raise ValueError("Caption text required when captions are enabled")
    if clean and total < len(clean) * 0.5:
        raise ValueError("At least half a second is required per caption line")
    return clean


def _srt_time(value):
    ms = max(0, round(value * 1000))
    hours, remaining = divmod(ms, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    seconds, milli = divmod(remaining, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milli:03}"


def captions_to_srt(lines, duration):
    """Space user-authored caption cards evenly; no speech-recognition claim."""
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid caption timeline duration")
    normalized = _captions(lines, "soft", duration)
    step = duration / len(normalized)
    return "\n".join(
        f"{i + 1}\n{_srt_time(i * step)} --> {_srt_time((i + 1) * step)}\n{text}\n"
        for i, text in enumerate(normalized)
    ) + "\n"


def _verify_settings(audio_mode, quality, caption_mode, caption_lines):
    if audio_mode not in AUDIO_MODES:
        raise ValueError("Invalid audio mode")
    if quality not in QUALITY:
        raise ValueError("Invalid export quality")
    if caption_mode not in CAPTION_MODES:
        raise ValueError("Invalid caption mode")
    if not isinstance(caption_lines, list):
        raise ValueError("Caption lines must be a list")
    return True


def exports(workspace_id, channel_id):
    media._channel(workspace_id, channel_id)
    initialize()
    with core.connect() as db:
        rows = db.execute("""
            SELECT * FROM assembly_exports WHERE workspace_id=? AND channel_id=?
              AND state='ready' ORDER BY created_at DESC, job_id DESC LIMIT 100
        """, (workspace_id, channel_id)).fetchall()
    return [dict(row) | {
        "candidate_ids": json.loads(row["candidate_ids_json"]),
        "caption_lines": json.loads(row["caption_lines_json"]),
        "youtube_uploaded": False,
    } for row in rows]


def export_job(workspace_id, channel_id, job_id, candidate_ids, quality="fast",
               audio_mode="preserve", caption_mode="none", caption_lines=None):
    """An explicitly approved local job assembles 1..8 selected clips in supplied order."""
    caption_lines = [] if caption_lines is None else caption_lines
    _verify_settings(audio_mode, quality, caption_mode, caption_lines)
    if (not isinstance(candidate_ids, list) or not 1 <= len(candidate_ids) <= MAX_CLIPS
            or any(not isinstance(i, int) or isinstance(i, bool) or i <= 0 for i in candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)):
        raise ValueError("Choose 1–8 distinct clip candidate IDs in playback order")
    initialize()
    media._channel(workspace_id, channel_id)
    media_pipeline.initialize()
    with core.connect() as db:
        job = db.execute("""
            SELECT id, state, format FROM production_jobs
            WHERE id=? AND workspace_id=? AND channel_id=?
        """, (job_id, workspace_id, channel_id)).fetchone()
        if job is None or job["state"] != "approved":
            raise ValueError("Production job must be approved in the selected channel")
        existing = db.execute("SELECT 1 FROM job_renders WHERE job_id=?", (job_id,)).fetchone()
        if existing:
            raise ValueError("This production job already has a legacy render")
        # Candidate IDs originate from the database; never trust filesystem paths in requests.
        rows = []
        for candidate_id in candidate_ids:
            row = db.execute("""
                SELECT c.id, c.start_seconds, c.duration_seconds,
                       m.filename, m.sha256, m.file_bytes, m.audio_codec
                FROM media_candidates c JOIN media_assets m ON m.id=c.asset_id
                WHERE c.id=? AND c.workspace_id=? AND c.channel_id=?
                  AND m.workspace_id=? AND m.channel_id=?
            """, (candidate_id, workspace_id, channel_id,
                  workspace_id, channel_id)).fetchone()
            if row is None:
                raise ValueError("Clip candidate not found in the selected channel")
            rows.append(dict(row))
    total = sum(row["duration_seconds"] for row in rows)
    if not math.isfinite(total) or total <= 0 or total > (180 if job["format"] == "short" else 1800):
        raise ValueError("Total clip time exceeds the approved format limit")
    clean_lines = _captions(caption_lines, caption_mode, total)
    # Verify each unique imported file once against its original SHA-256.
    source_cache = {}
    for row in rows:
        key = (row["filename"], row["sha256"])
        if key not in source_cache:
            source_cache[key] = media._validated_source(row)
    segments = [
        {"source": source_cache[(row["filename"], row["sha256"])],
         "start": float(row["start_seconds"]), "seconds": float(row["duration_seconds"]),
         "has_audio": bool(row["audio_codec"])}
        for row in rows
    ]
    editor.OUT.mkdir(parents=True, exist_ok=True)
    target = editor.OUT / f"assembly_job_{job_id}_{uuid.uuid4().hex[:12]}.mp4"
    # The unique job_id claim blocks concurrent and duplicate exports.
    with core.connect() as db:
        try:
            db.execute("""
                INSERT INTO assembly_exports(job_id,workspace_id,channel_id,state,
                  candidate_ids_json,caption_lines_json,caption_mode,audio_mode,quality,total_seconds)
                VALUES(?,?,?,'rendering',?,?,?,?,?,?)
            """, (job_id, workspace_id, channel_id, json.dumps(candidate_ids),
                  json.dumps(clean_lines, ensure_ascii=False), caption_mode,
                  audio_mode, quality, total))
        except __import__("sqlite3").IntegrityError as exc:
            raise ValueError("This job already has an assembly or active export") from exc
    try:
        output = render_assembled_video(
            segments, target, job["format"], quality, audio_mode, caption_mode, clean_lines)
        if not Path(output).is_file() or Path(output).stat().st_size <= 0:
            raise RuntimeError("Assembler did not produce a complete video")
        with core.connect() as db:
            db.execute("""UPDATE assembly_exports SET state='ready',output_path=?
                          WHERE job_id=? AND workspace_id=?""",
                       (str(output), job_id, workspace_id))
            db.execute("""INSERT INTO audit_log(workspace_id,channel_id,job_id,action,detail)
                          VALUES(?,?,?,'assembly_exported',?)""",
                       (workspace_id, channel_id, job_id, Path(output).name))
    except Exception:
        target.unlink(missing_ok=True)
        with core.connect() as db:
            db.execute("DELETE FROM assembly_exports WHERE job_id=? AND workspace_id=? AND state='rendering'",
                       (job_id, workspace_id))
        raise
    return {"job_id": job_id, "workspace_id": workspace_id, "channel_id": channel_id,
            "state": "ready", "output_path": str(output),
            "quality": quality, "audio_mode": audio_mode, "caption_mode": caption_mode,
            "clip_count": len(segments), "total_seconds": total, "youtube_uploaded": False}


def render_assembled_video(segments, target, preset, quality, audio_mode, caption_mode, caption_lines):
    """FFmpeg encode segments -> concat -> add optional captions -> atomic publish."""
    _verify_settings(audio_mode, quality, caption_mode, caption_lines)
    if preset not in ("short", "long") or not segments or len(segments) > MAX_CLIPS:
        raise ValueError("Invalid video assembly preset or clip count")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required for video assembly")
    target = Path(target).resolve()
    if target.parent != editor.OUT.resolve() or target.suffix.lower() != ".mp4":
        raise ValueError("Video output must be an MP4 in media/output")
    if target.exists():
        raise ValueError("Output file already exists")
    total = sum(float(seg["seconds"]) for seg in segments)
    clean_lines = _captions(caption_lines, caption_mode, total)
    width, height = QUALITY[quality][preset]
    encoding_preset, crf = QUALITY[quality]["preset"], QUALITY[quality]["crf"]
    # Single constant resolution/frame-rate and audio format permits safe concat copy.
    vf = (f"scale={width}:{height}:force_original_aspect_ratio="
          f"{'increase' if preset == 'short' else 'decrease'},"
          + (f"crop={width}:{height}" if preset == "short" else
             f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2")
          + ",setsar=1,fps=30,format=yuv420p")
    editor.OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".assembly_", dir=editor.OUT) as workspace:
        scratch = Path(workspace)
        parts = []
        for index, segment in enumerate(segments):
            source = Path(segment["source"])
            start, seconds = float(segment["start"]), float(segment["seconds"])
            if (not source.is_file() or not all(math.isfinite(n) for n in (start, seconds))
                    or start < 0 or seconds <= 0 or seconds > 120):
                raise ValueError("Invalid source segment")
            out = scratch / f"part_{index:03}.mp4"
            synthetic = audio_mode == "mute" or not segment["has_audio"]
            cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-ss", str(start), "-i", str(source),
                   "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                   "-t", str(seconds), "-map", "0:v:0",
                   "-map", "1:a:0" if synthetic else "0:a:0",
                   "-vf", vf, "-r", "30", "-pix_fmt", "yuv420p",
                   "-c:v", "libx264", "-preset", encoding_preset, "-crf", crf,
                   "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
            if not synthetic:
                filter_value = "apad" if audio_mode == "preserve" else "loudnorm=I=-16:TP=-1.5:LRA=11,apad"
                cmd += ["-af", filter_value]
            cmd += ["-movflags", "+faststart", str(out)]
            subprocess.run(cmd, check=True, timeout=max(90, min(3600, round(seconds * 30))))
            parts.append(out)
        manifest = scratch / "segments.txt"
        # Filenames below are generated, never user-supplied or absolute.
        manifest.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
        joined = scratch / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "1", "-i", str(manifest), "-c", "copy",
                        "-movflags", "+faststart", str(joined)], check=True, timeout=180)
        result = joined
        if caption_mode != "none":
            captions = scratch / "captions.srt"
            captions.write_text(captions_to_srt(clean_lines, total), encoding="utf-8")
            staged = scratch / "captioned.mp4"
            if caption_mode == "soft":
                cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-i", str(joined), "-i", str(captions),
                       "-map", "0:v:0", "-map", "0:a:0", "-map", "1:0",
                       "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                       "-movflags", "+faststart", str(staged)]
                subprocess.run(cmd, check=True, timeout=180)
            else:
                # Work inside a generated directory so the FFmpeg subtitles
                # filter receives a fixed relative filename (Windows-safe).
                cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-i", str(joined), "-map", "0:v:0", "-map", "0:a:0",
                       "-vf", "subtitles=captions.srt", "-c:v", "libx264",
                       "-preset", encoding_preset, "-crf", crf, "-c:a", "copy",
                       "-movflags", "+faststart", str(staged)]
                subprocess.run(cmd, check=True, cwd=workspace,
                               timeout=max(180, min(3600, round(total * 30))))
            result = staged
        os.replace(result, target)
    return str(target)
