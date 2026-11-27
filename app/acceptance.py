"""Local acceptance runner. Temporary data only; no cloud or YouTube operations."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import time

from app import editor, platform_core as core, production_operator as operator
from app import media_intelligence as media, render_queue as queue
from app import postproduction as post, video_assembly as assembly, maintenance


class AcceptanceError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AcceptanceError(message)


@contextmanager
def isolated(root):
    previous = core.DB, editor.RAW, editor.OUT
    core.DB, editor.RAW, editor.OUT = root / "platform.sqlite3", root / "raw", root / "output"
    try:
        editor.RAW.mkdir()
        editor.OUT.mkdir()
        yield
    finally:
        core.DB, editor.RAW, editor.OUT = previous


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True, timeout=60, capture_output=True)


def run(footage=None):
    report = {"schema": 1, "status": "failed", "input_kind": "synthetic" if footage is None else "user_footage",
              "platform": platform.system(), "os_release": platform.release(), "python": platform.python_version(),
              "logical_cpus": os.cpu_count(), "steps": [], "live_youtube_verified": False,
              "optional_ai_verified": False}

    @contextmanager
    def stage(name):
        start = time.perf_counter()
        item = {"name": name, "status": "failed"}
        report["steps"].append(item)
        try:
            yield
            item["status"] = "passed"
        except Exception:
            report["failed_stage"] = name
            raise
        finally:
            item["wall_seconds"] = round(time.perf_counter() - start, 3)

    try:
        with stage("prerequisites"):
            require(all(shutil.which(name) for name in ("ffmpeg", "ffprobe")), "FFmpeg and FFprobe must be on PATH")
        with stage("input"):
            original = None
            if footage is not None:
                original = Path(footage).resolve()
                require(original.is_file() and original.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"),
                        "Choose an existing local video file")
                require(0 < original.stat().st_size <= 250 * 1024**2, "Use a video sample no larger than 250 MiB")
        with tempfile.TemporaryDirectory(prefix="autopilot-acceptance-") as folder, isolated(Path(folder).resolve()):
            with stage("initialize"):
                report["free_disk_gib"] = round(shutil.disk_usage(folder).free / 1024**3, 2)
                require(report["free_disk_gib"] >= 0.5, "At least 512 MiB free temporary disk space is required")
                version = subprocess.run(["ffmpeg", "-version"], check=True, timeout=10,
                                         capture_output=True, text=True)
                report["ffmpeg"] = version.stdout.splitlines()[0]
                core.initialize()
                operator.initialize()
                post.initialize()
                w = core.new_workspace("Acceptance sandbox")
                c = core.new_channel(w, "Test channel", "gaming", "Hinglish")
            with stage("import"):
                name = "sample" + (original.suffix.lower() if original else ".mp4")
                source = editor.RAW / name
                if original:
                    shutil.copyfile(original, source)
                else:
                    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=4",
                           "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-shortest", str(source))
                asset = media.import_media(w, c, name)
                require(asset["duration_seconds"] >= 2, "Choose a sample at least two seconds long")
            with stage("plan_and_rank"):
                task = operator.schedule(w, c, "Local acceptance sample", "short", asset_id=asset["id"],
                                         clip_seconds=2, scan_seconds=12)
                result = operator.run_once()
                require(result is not None and result["state"] == "review" and bool(result["candidate_ids"]),
                        "Planner did not produce a reviewable draft and clips")
                job = result["job_id"]
                require(core.jobs(w)[0]["state"] == "ready_for_review", "Review gate missing")
                report["suggested_clips"] = len(result["candidate_ids"])
                try:
                    operator.queue_recommended(w, c, task["id"])
                except ValueError:
                    pass
                else:
                    raise AcceptanceError("Unapproved render was accepted")
            with stage("approve_and_queue"):
                core.transition(w, job, "approved")
                queued = operator.queue_recommended(w, c, task["id"])
                require(queued["state"] == "pending", "Queue did not persist the reviewed job")
                # Simulate an interrupted claim before encoding; no worker is killed.
                with core.connect() as db:
                    db.execute("UPDATE render_tasks SET state='running' WHERE job_id=?", (job,))
                queue.recover()
                require(queue.list_tasks(w, c)[0]["state"] == "interrupted", "Interrupted claim not detected")
                queue.retry(w, c, job)
            with stage("render"):
                start = time.perf_counter()
                rendered = queue.run_once()
                elapsed = time.perf_counter() - start
                require(rendered is not None and rendered["state"] == "ready", "Local render worker failed")
                original_export = assembly.export_file(w, c, job)
                export = assembly.exports(w, c)[0]
                probe = assembly.probe_output(original_export)
                video = next(s for s in probe["streams"] if s["codec_type"] == "video")
                duration = float(probe["format"]["duration"])
                report["render"] = {"seconds": round(duration, 3), "wall_seconds": round(elapsed, 3),
                                    "width": video["width"], "height": video["height"],
                                    "bytes": original_export.stat().st_size}
                assembly.validate_output(original_export, "short", "fast", "none", export["total_seconds"])
            with stage("finish"):
                srt = post.to_srt([(0.1, 1.0, "Acceptance sample")])
                post.attach_captions(w, c, job, srt)
                voice = editor.RAW / "test-tone.wav"
                ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(voice))
                post.mix_voiceover(w, c, job, voice.name, 0.25, 1.0)
                final = assembly.export_file(w, c, job)
                assembly.validate_output(final, "short", "fast", "soft", export["total_seconds"])
                post.create_thumbnail(w, c, job, 0.5)
                require(post.thumbnail_file(w, c, job).read_bytes().startswith(b"\xff\xd8"),
                        "Thumbnail is not a JPEG")
                report["revisions"] = len(post.history(w, c, job))
                require(report["revisions"] == 3 and original_export.is_file(), "Original revision was lost")
            with stage("backup_and_isolation"):
                other_w = core.new_workspace("Other sandbox")
                other_c = core.new_channel(other_w, "Other channel", "gaming")
                require(not assembly.exports(other_w, other_c), "Export leaked between workspaces")
                snapshot = maintenance.backup_database(core.DB, Path(folder) / "snapshot.sqlite3")
                require(snapshot.is_file(), "Backup not created")
                with core.connect() as db:
                    require(db.execute("SELECT count(*) FROM youtube_uploads").fetchone()[0] == 0,
                            "Unexpected upload record")
                    require(db.execute("SELECT count(*) FROM youtube_links").fetchone()[0] == 0,
                            "Unexpected linked account")
                    require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity failure")
        report["status"] = "passed"
    except Exception as exc:
        report.setdefault("failed_stage", "isolation_cleanup")
        report["error_type"] = type(exc).__name__
        # Report may be shared; never include filesystem paths or provider error contents.
        if isinstance(exc, AcceptanceError):
            report["reason"] = str(exc)
        else:
            report["reason"] = "Local step failed; inspect the failed stage and verify the input and dependencies."
    return report


def main():
    parser = argparse.ArgumentParser(description="Run an isolated, offline local production acceptance test")
    parser.add_argument("--footage", type=Path, help="Optional existing video sample up to 250 MiB; copied temporarily")
    parser.add_argument("--report", type=Path, help="Write a new UTF-8 JSON report; existing files are never overwritten")
    args = parser.parse_args()
    report = run(args.footage)
    payload = json.dumps(report, indent=2) + "\n"
    if args.report is not None:
        try:
            with args.report.open("x", encoding="utf-8") as output:
                output.write(payload)
        except OSError:
            parser.exit(2, "Could not create report file; choose a new writable filename.\n")
    print(payload, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
