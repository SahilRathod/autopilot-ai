"""Durable local assembly queue. One worker per database; no cloud service."""
import argparse
from contextlib import contextmanager
import json
import os
import time

from app import platform_core as core, media_intelligence as media
from app import video_assembly as assembly, media_pipeline


def initialize():
    assembly.initialize()
    media_pipeline.initialize()
    with core.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS render_tasks (
            job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id),
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            state TEXT NOT NULL CHECK(state IN ('pending','running','ready','failed','interrupted')),
            request_json TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_render_tasks_state ON render_tasks(state, created_at)")


@contextmanager
def worker_lock():
    """OS-released lock, including on process termination. Local filesystem only."""
    path = core.DB.with_suffix(".worker.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another local render worker is active") from exc
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _record(row):
    return {k: row[k] for k in ("job_id", "workspace_id", "channel_id", "state",
                                "attempts", "error", "created_at", "updated_at")}


def list_tasks(workspace_id, channel_id):
    media._channel(workspace_id, channel_id)
    initialize()
    with core.connect() as db:
        return [_record(r) for r in db.execute(
            """SELECT * FROM render_tasks WHERE workspace_id=? AND channel_id=?
               ORDER BY created_at DESC, job_id DESC LIMIT 100""", (workspace_id, channel_id))]


def enqueue(workspace_id, channel_id, job_id, candidate_ids, quality="fast",
            audio_mode="preserve", caption_mode="none", caption_lines=None):
    initialize()
    _, _, _, lines = assembly.prepare_job(workspace_id, channel_id, job_id, candidate_ids,
                                          quality, audio_mode, caption_mode, caption_lines)
    request = dict(candidate_ids=candidate_ids, quality=quality, audio_mode=audio_mode,
                   caption_mode=caption_mode, caption_lines=lines)
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("""SELECT 1 FROM production_jobs WHERE id=? AND workspace_id=?
                          AND channel_id=? AND state='approved'""",
                          (job_id, workspace_id, channel_id)).fetchone():
            raise ValueError("Job must be approved")
        for table in ("job_renders", "assembly_exports", "render_tasks"):
            if db.execute("SELECT 1 FROM " + table + " WHERE job_id=?", (job_id,)).fetchone():
                raise ValueError("Job already has a render or queued task")
        db.execute("""INSERT INTO render_tasks(job_id,workspace_id,channel_id,state,request_json)
                      VALUES(?,?,?,'pending',?)""",
                   (job_id, workspace_id, channel_id, json.dumps(request, ensure_ascii=False)))
        return _record(db.execute("SELECT * FROM render_tasks WHERE job_id=?", (job_id,)).fetchone())


def retry(workspace_id, channel_id, job_id):
    initialize()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("""SELECT * FROM render_tasks WHERE job_id=? AND workspace_id=?
                         AND channel_id=?""", (job_id, workspace_id, channel_id)).fetchone()
        if not row or row["state"] not in ("failed", "interrupted"):
            raise ValueError("Only failed or interrupted tasks can be retried")
        if db.execute("SELECT 1 FROM assembly_exports WHERE job_id=?", (job_id,)).fetchone():
            raise ValueError("Unresolved export claim; stop all encoders and review before recovery")
        if not db.execute("SELECT 1 FROM production_jobs WHERE id=? AND state='approved'", (job_id,)).fetchone():
            raise ValueError("Job must remain approved")
        db.execute("""UPDATE render_tasks SET state='pending',error=NULL,
                      updated_at=CURRENT_TIMESTAMP WHERE job_id=?""", (job_id,))
        return _record(db.execute("SELECT * FROM render_tasks WHERE job_id=?", (job_id,)).fetchone())


def _recover():
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Do not delete active-looking encoder claims: an orphan FFmpeg child can survive a crash.
        # Reconcile already-committed exports; require manual review for ambiguous interruptions.
        db.execute("""UPDATE render_tasks SET state='ready',error=NULL,updated_at=CURRENT_TIMESTAMP
                      WHERE state='running' AND EXISTS
                      (SELECT 1 FROM assembly_exports e WHERE e.job_id=render_tasks.job_id AND e.state='ready')""")
        db.execute("""UPDATE render_tasks SET state='interrupted',
                      error='Worker stopped before completion; review before retry',
                      updated_at=CURRENT_TIMESTAMP WHERE state='running'""")


def recover():
    initialize()
    with worker_lock():
        _recover()


def run_once():
    initialize()
    with worker_lock():
        _recover()
        with core.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM render_tasks WHERE state='pending'
                              ORDER BY created_at,job_id LIMIT 1""").fetchone()
            if row is None:
                return None
            job_id = row["job_id"]
            db.execute("""UPDATE render_tasks SET state='running',attempts=attempts+1,
                          updated_at=CURRENT_TIMESTAMP WHERE job_id=?""", (job_id,))
        try:
            assembly.export_job(row["workspace_id"], row["channel_id"], job_id,
                                **json.loads(row["request_json"]), _queue_worker=True)
            state, error = "ready", None
        except Exception as exc:
            state, error = "failed", (str(exc) or type(exc).__name__)[:500]
        with core.connect() as db:
            db.execute("""UPDATE render_tasks SET state=?,error=?,updated_at=CURRENT_TIMESTAMP
                          WHERE job_id=?""", (state, error, job_id))
            return _record(db.execute("SELECT * FROM render_tasks WHERE job_id=?", (job_id,)).fetchone())


def main():
    parser = argparse.ArgumentParser(description="Persistent local video render worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job")
    args = parser.parse_args()
    core.initialize()
    media.initialize()
    while True:
        try:
            result = run_once()
            if result:
                print(json.dumps(result), flush=True)
            if args.once:
                break
            if result is None:
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except RuntimeError as exc:
            parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
