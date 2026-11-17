"""V0.5 M3: offline, explainable audio/visual clip ranking, not event recognition.

This module never calls cloud APIs or invents detected kills, wins or other gameplay
events. Tactical/sandbox/balanced are user-selected HEURISTIC WEIGHT PRESETS.
"""
from array import array
import json
import math
import shutil
import statistics
import subprocess
import sys

from app import media_intelligence as media, platform_core as core

AUDIO_RATE = 8000
BIN_SECONDS = 0.5
BIN_SAMPLES = int(AUDIO_RATE * BIN_SECONDS)
MAX_SECONDS = 600
WEIGHTS = {
    "balanced": (0.5, 0.5),
    "tactical": (0.75, 0.25),
    "sandbox": (0.25, 0.75),
}


def initialize():
    # Ranking is scoped per source and profile. A source rescan deletes its old
    # candidates; FK cascades remove only the corresponding obsolete rankings.
    with core.connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS candidate_rankings (
            candidate_id INTEGER NOT NULL REFERENCES media_candidates(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            asset_id INTEGER NOT NULL REFERENCES media_assets(id),
            profile TEXT NOT NULL CHECK(profile IN ('balanced','tactical','sandbox')),
            score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
            audio_score REAL NOT NULL CHECK(audio_score BETWEEN 0 AND 1),
            visual_score REAL NOT NULL CHECK(visual_score BETWEEN 0 AND 1),
            audio_analyzed INTEGER NOT NULL CHECK(audio_analyzed IN (0, 1)),
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(candidate_id, profile)
        );
        CREATE INDEX IF NOT EXISTS idx_rankings_scope
          ON candidate_rankings(workspace_id,channel_id,asset_id,profile,score DESC);
        """)


def _validate_profile(profile):
    if profile not in WEIGHTS:
        raise ValueError("Unknown ranking profile. Choose balanced, tactical or sandbox.")


def _validate_seconds(seconds):
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= MAX_SECONDS:
        raise ValueError("Audio analysis must be between 0 and 600 seconds")
    return float(seconds)


def decode_audio_levels(source, seconds):
    """Decode a bounded mono 8kHz PCM segment into half-second RMS bins.

    Uses standard-library array rather than Python's removed audioop module.
    No external AI dependencies or audio files are written.
    """
    duration = _validate_seconds(seconds)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required for audio-intensity analysis")
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(source), "-t", str(duration),
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-ac", "1", "-ar", str(AUDIO_RATE),
        "-f", "s16le", "pipe:1",
    ]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True,
            timeout=min(180, int(duration) + 30),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Could not decode source audio; check the video and its audio track") from exc
    raw = result.stdout
    # FFmpeg output is limited by duration and sample rate: max ~9.6MB.
    max_bytes = math.ceil(duration * AUDIO_RATE) * 2 + 2 * AUDIO_RATE
    if len(raw) > max_bytes or len(raw) % 2:
        raise ValueError("Unexpected PCM audio size from FFmpeg")
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    bins = []
    for offset in range(0, len(samples), BIN_SAMPLES):
        segment = samples[offset:offset + BIN_SAMPLES]
        if segment:
            rms = math.sqrt(sum(int(v) * int(v) for v in segment) / len(segment)) / 32768
            bins.append(min(1.0, rms))
    return bins


def _transient_score(levels, start, duration):
    """Relative RMS spike strength within a candidate clip, 0..1.

    Flat consistently loud background tracks are not treated as transient events.
    """
    if not levels:
        return 0.0
    baseline = statistics.median(levels)
    highest = max(levels)
    spread = highest - baseline
    if spread <= 0.005:
        return 0.0
    first = max(0, min(len(levels), int(start / BIN_SECONDS)))
    last = max(first + 1, min(len(levels), math.ceil((start + duration) / BIN_SECONDS)))
    window = levels[first:last]
    if not window:
        return 0.0
    return max(0.0, min(1.0, (max(window) - baseline) / spread))


def _candidate_score(candidate, levels, profile, audio_analyzed):
    weight_audio, weight_visual = WEIGHTS[profile]
    visual = 0.65 if candidate["reason"] == "scene_change" else 0.25
    audio = _transient_score(levels, candidate["start_seconds"], candidate["duration_seconds"]) if audio_analyzed else 0.0
    if not audio_analyzed:
        weight_audio, weight_visual = 0.0, 1.0
    score = round(100 * (weight_audio * audio + weight_visual * visual))
    reasons = [
        ("Visual scene transition candidate" if candidate["reason"] == "scene_change"
         else "Opening context clip; no scene transition required"),
    ]
    if not audio_analyzed:
        transient = "unavailable"
        reasons.append("No audio track or usable audio; ranked by visual cues only")
    elif audio >= 0.55:
        transient = "elevated"
        reasons.append("Relative audio energy spike inside this clip window")
    else:
        transient = "low"
        reasons.append("No strong relative audio transient in this clip window")
    evidence = {
        "signals": {"audio_transient": transient,
                    "visual_transition": candidate["reason"] == "scene_change"},
        "reasons": reasons,
        "claims": "visual and audio heuristics only",
    }
    return {
        "candidate_id": candidate["id"],
        "asset_id": candidate["asset_id"],
        "start_seconds": candidate["start_seconds"],
        "duration_seconds": candidate["duration_seconds"],
        "reason": candidate["reason"],
        "profile": profile,
        "score": score,
        "audio_score": round(audio, 4),
        "visual_score": visual,
        "audio_analyzed": bool(audio_analyzed),
        "evidence": evidence,
    }


def rankings(workspace_id, channel_id, asset_id, profile="balanced"):
    _validate_profile(profile)
    media.asset(workspace_id, channel_id, asset_id)
    initialize()
    with core.connect() as db:
        rows = db.execute("""
            SELECT r.*, c.start_seconds,c.duration_seconds,c.reason
            FROM candidate_rankings r
            JOIN media_candidates c ON r.candidate_id=c.id
            WHERE r.workspace_id=? AND r.channel_id=? AND r.asset_id=? AND r.profile=?
            ORDER BY r.score DESC, c.start_seconds, r.candidate_id
        """, (workspace_id, channel_id, asset_id, profile)).fetchall()
    return [{
        "candidate_id": row["candidate_id"],
        "asset_id": row["asset_id"],
        "start_seconds": row["start_seconds"],
        "duration_seconds": row["duration_seconds"],
        "reason": row["reason"],
        "profile": row["profile"],
        "score": row["score"],
        "audio_score": row["audio_score"],
        "visual_score": row["visual_score"],
        "audio_analyzed": bool(row["audio_analyzed"]),
        "evidence": json.loads(row["evidence_json"]),
    } for row in rows]


def rank_asset(workspace_id, channel_id, asset_id, profile="balanced", max_seconds=120):
    _validate_profile(profile)
    limit = _validate_seconds(max_seconds)
    record = media.asset(workspace_id, channel_id, asset_id)
    candidates = media.candidates(workspace_id, channel_id, asset_id)
    if not candidates:
        raise ValueError("Scan footage before ranking its clips")
    # Ensure the original file was not replaced after import or during analysis.
    source = media._validated_source(record)
    levels = []
    analyzed = bool(record["audio_codec"])
    if analyzed:
        duration = min(float(record["duration_seconds"]), limit)
        levels = decode_audio_levels(source, duration)
        # A silent or steady music bed has no meaningful transient signal.
        # Fall back to visual weights instead of unfairly suppressing scores.
        analyzed = bool(levels) and (max(levels) - statistics.median(levels) > 0.005)
    media._validated_source(record)

    results = [_candidate_score(candidate, levels, profile, analyzed) for candidate in candidates]
    results.sort(key=lambda row: (-row["score"], row["start_seconds"], row["candidate_id"]))
    initialize()
    with core.connect() as db:
        # Delete and insert in one transaction. A rescan cascades scores from
        # deleted candidate IDs. The result is scoped to the same workspace.
        db.execute("""DELETE FROM candidate_rankings
                      WHERE workspace_id=? AND channel_id=? AND asset_id=? AND profile=?""",
                   (workspace_id, channel_id, asset_id, profile))
        db.executemany("""
            INSERT INTO candidate_rankings
              (candidate_id,workspace_id,channel_id,asset_id,profile,score,
               audio_score,visual_score,audio_analyzed,evidence_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, [
            (r["candidate_id"], workspace_id, channel_id, asset_id, profile, r["score"],
             r["audio_score"], r["visual_score"], int(r["audio_analyzed"]),
             json.dumps(r["evidence"]))
            for r in results
        ])
        db.execute("""INSERT INTO audit_log(workspace_id,channel_id,action,detail)
                      VALUES(?,?,?,?)""",
                   (workspace_id, channel_id, "media_ranked", f"{asset_id}:{profile}"))
    return results
