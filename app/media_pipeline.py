"""Manual, local FFmpeg render handoff for approved platform production jobs."""
import uuid
from app import platform_core as core, editor


def initialize():
    with core.connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS job_renders (
          job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id),
          workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
          channel_id INTEGER NOT NULL REFERENCES channels(id),
          state TEXT NOT NULL CHECK(state IN ('rendering','ready')),
          output_path TEXT, source_name TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)


def render_job(workspace_id, job_id, source_name, start=0.0, seconds=30.0):
    """Render once per approved job, without publishing or modifying job approval state."""
    initialize()
    if not isinstance(source_name, str) or not source_name:
        raise ValueError("Media source filename required")
    if seconds <= 0 or start < 0:
        raise ValueError("Invalid media clipping time")
    editor.source(source_name)
    with core.connect() as db:
        # Serialize competing legacy and assembled-render claims across processes.
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("SELECT * FROM production_jobs WHERE id=? AND workspace_id=?",
                         (job_id, workspace_id)).fetchone()
        if job is None:
            raise ValueError("Job not found in this workspace")
        if job["state"] != "approved":
            raise ValueError("Job must be approved before media rendering")
        table_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='assembly_exports'"
        ).fetchone()
        if table_exists and db.execute(
            "SELECT 1 FROM assembly_exports WHERE job_id=? AND workspace_id=?",
            (job_id,workspace_id)
        ).fetchone():
            raise ValueError("This job already has an assembled export or active assembly")
        try:
            db.execute("""INSERT INTO job_renders(job_id,workspace_id,channel_id,state,source_name)
                       VALUES(?,?,?,'rendering',?)""",
                       (job_id,workspace_id,job["channel_id"],source_name))
        except __import__("sqlite3").IntegrityError as exc:
            raise ValueError("This job already has a render or active render claim") from exc
        vertical = job["format"] == "short"
    # The randomized name prevents accidental overwrites when two jobs render simultaneously.
    output_name = f"job_{job_id}_{uuid.uuid4().hex[:12]}.mp4"
    try:
        output = editor.highlight(source_name, start, seconds, vertical, output_name)
        with core.connect() as db:
            db.execute("""UPDATE job_renders SET state='ready',output_path=?
                        WHERE job_id=? AND workspace_id=?""",
                       (output,job_id,workspace_id))
            db.execute("""INSERT INTO audit_log(workspace_id,channel_id,job_id,action,detail)
                        VALUES(?,?,?,'media_rendered',?)""",
                       (workspace_id,job["channel_id"],job_id,output_name))
    except Exception:
        # A crash may leave a rendering claim; explicit recovery is required to avoid races.
        with core.connect() as db:
            db.execute("DELETE FROM job_renders WHERE job_id=? AND workspace_id=? AND state='rendering'",
                       (job_id,workspace_id))
        raise
    return {"workspace_id": workspace_id, "job_id": job_id, "state": "ready",
            "output_path": output, "youtube_uploaded": False}
