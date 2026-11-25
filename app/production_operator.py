"""Durable offline content schedule. Creates reviewed drafts; never publishes."""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

from app import ai_director as ai, platform_core as core, media_intelligence as media
from app import highlight_ranker as ranker, render_queue


def initialize():
    ai.initialize()
    media.initialize()
    ranker.initialize()
    render_queue.initialize()
    with core.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS operator_tasks(
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id), topic TEXT NOT NULL,
            format TEXT NOT NULL, due_at TEXT NOT NULL, asset_id INTEGER,
            clip_seconds REAL NOT NULL, scan_seconds REAL NOT NULL, profile TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('pending','running','review','failed','interrupted','cancelled')),
            job_id INTEGER REFERENCES production_jobs(id), candidate_ids_json TEXT NOT NULL DEFAULT '[]',
            error TEXT, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_operator_due ON operator_tasks(state,due_at,id)")


def _now():
    return datetime.now(timezone.utc)


def _utc(value):
    now=_now()
    if value is None:
        return now.isoformat(timespec="seconds")
    try:
        due=datetime.fromisoformat(value.replace("Z","+00:00"))
        if due.tzinfo is None:
            raise ValueError()
        due=due.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError) as exc:
        raise ValueError("Supply a timezone-aware schedule timestamp") from exc
    if due>now+timedelta(days=365):
        raise ValueError("Schedule within the next year")
    return due.isoformat(timespec="seconds")


def _public(row):
    result=dict(row)
    result["candidate_ids"]=json.loads(result.pop("candidate_ids_json"))
    return result


def schedule(w,c,topic,fmt,due_at=None,asset_id=None,clip_seconds=30,scan_seconds=120,profile="balanced"):
    initialize()
    ai.channel(w,c)
    if not isinstance(topic,str) or not 3<=len(topic.strip())<=180 or fmt not in ("short","long"):
        raise ValueError("Invalid topic or format")
    if profile not in ("balanced","tactical","sandbox"):
        raise ValueError("Invalid ranking profile")
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (clip_seconds,scan_seconds)) or not (
            1<=clip_seconds<=120 and 2<=scan_seconds<=600):
        raise ValueError("Invalid scan or clip duration")
    if asset_id is not None:
        media.asset(w,c,asset_id)
    due=_utc(due_at)
    with core.connect() as db:
        cur=db.execute("""INSERT INTO operator_tasks(workspace_id,channel_id,topic,format,due_at,asset_id,
            clip_seconds,scan_seconds,profile,state) VALUES(?,?,?,?,?,?,?,?,?,'pending')""",
            (w,c,topic.strip(),fmt,due,asset_id,clip_seconds,scan_seconds,profile))
        return _public(db.execute("SELECT * FROM operator_tasks WHERE id=?",(cur.lastrowid,)).fetchone())


def tasks(w,c):
    initialize()
    ai.channel(w,c)
    with core.connect() as db:
        return [_public(r) for r in db.execute("""SELECT * FROM operator_tasks WHERE workspace_id=? AND channel_id=?
            ORDER BY due_at DESC,id DESC LIMIT 100""",(w,c))]


def _get(db,w,c,task):
    row=db.execute("SELECT * FROM operator_tasks WHERE id=? AND workspace_id=? AND channel_id=?",(task,w,c)).fetchone()
    if not row:
        raise ValueError("Operator task not found in channel")
    return row


def cancel(w,c,task):
    initialize()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=_get(db,w,c,task)
        if row["state"]!="pending":
            raise ValueError("Only pending tasks can be cancelled")
        db.execute("UPDATE operator_tasks SET state='cancelled' WHERE id=?",(task,))
        return _public(_get(db,w,c,task))


def retry(w,c,task):
    initialize()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=_get(db,w,c,task)
        if row["state"] not in ("failed","interrupted") or row["job_id"] is not None:
            raise ValueError("Only unfinished failed/interrupted tasks may be retried")
        db.execute("UPDATE operator_tasks SET state='pending',error=NULL WHERE id=?",(task,))
        return _public(_get(db,w,c,task))


def _suggest(row):
    if row["asset_id"] is None:
        return []
    w,c,asset=row["workspace_id"],row["channel_id"],row["asset_id"]
    candidates=media.candidates(w,c,asset)
    # Never rescan existing candidates and invalidate somebody's reviewed edits.
    if not candidates:
        media.scan_media(w,c,asset,row["clip_seconds"],.35,row["scan_seconds"])
        candidates=media.candidates(w,c,asset)
    ranked=ranker.rank_asset(w,c,asset,row["profile"],row["scan_seconds"])
    scores={r["candidate_id"]:r["score"] for r in ranked}
    ordered=sorted(candidates,key=lambda x:(-scores.get(x["id"],0),x["start_seconds"],x["id"]))
    selected=[]; total=0
    limit=180 if row["format"]=="short" else 960
    for clip in ordered:
        start,end=clip["start_seconds"],clip["start_seconds"]+clip["duration_seconds"]
        if total+clip["duration_seconds"]>limit:
            continue
        if any(start<old["start_seconds"]+old["duration_seconds"] and end>old["start_seconds"] for old in selected):
            continue
        selected.append(clip);total+=clip["duration_seconds"]
        if len(selected)>=3:
            break
    return [r["id"] for r in sorted(selected,key=lambda x:x["start_seconds"])]


def _execute(row):
    w,c,task=row["workspace_id"],row["channel_id"],row["id"]
    ch=ai.channel(w,c)
    pack=ai.validate_pack(ai.offline(ch,row["topic"],row["format"],ai.memory(w,c)))
    candidate_ids=_suggest(row)
    fingerprint=hashlib.sha256(f"operator:{task}:{w}:{c}".encode()).hexdigest()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current=_get(db,w,c,task)
        if current["state"]!="running" or current["job_id"] is not None:
            raise ValueError("Operator task is no longer active")
        job=db.execute("""INSERT INTO production_jobs(workspace_id,channel_id,title,format,state)
            VALUES(?,?,?,?,'ready_for_review')""",(w,c,pack["title"][:200],row["format"])).lastrowid
        db.execute("""INSERT INTO ai_drafts(workspace_id,channel_id,provider,topic,format,fingerprint,result_json,job_id)
            VALUES(?,?,'offline',?,?,?,?,?)""",(w,c,row["topic"],row["format"],fingerprint,
                                                json.dumps(pack,ensure_ascii=False),job))
        db.execute("""UPDATE operator_tasks SET state='review',job_id=?,candidate_ids_json=?,error=NULL
            WHERE id=?""",(job,json.dumps(candidate_ids),task))
        db.execute("""INSERT INTO audit_log(workspace_id,channel_id,job_id,action,detail)
            VALUES(?,?,?,'operator_draft_ready',?)""",(w,c,job,str(task)))
        return _public(_get(db,w,c,task))


def run_once():
    initialize()
    with render_queue.worker_lock(".operator-worker.lock"):
        with core.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE operator_tasks SET state='interrupted',
                error='Worker interrupted; retry to prepare the draft' WHERE state='running'""")
            row=db.execute("""SELECT * FROM operator_tasks WHERE state='pending' AND due_at<=?
                ORDER BY due_at,id LIMIT 1""",(_now().isoformat(timespec="seconds"),)).fetchone()
            if not row:
                return None
            db.execute("UPDATE operator_tasks SET state='running',attempts=attempts+1 WHERE id=?",(row["id"],))
        try:
            return _execute(row)
        except Exception as exc:
            with core.connect() as db:
                db.execute("UPDATE operator_tasks SET state='failed',error=? WHERE id=?",
                           (str(exc)[:400] or type(exc).__name__,row["id"]))
                return _public(_get(db,row["workspace_id"],row["channel_id"],row["id"]))


def queue_recommended(w,c,task):
    initialize()
    with core.connect() as db:
        row=_get(db,w,c,task)
        if row["state"]!="review" or row["job_id"] is None:
            raise ValueError("Prepare a review job first")
        ids=json.loads(row["candidate_ids_json"])
        if not ids:
            raise ValueError("No suggested footage; choose footage in Media Studio")
        job=db.execute("SELECT state FROM production_jobs WHERE id=? AND workspace_id=? AND channel_id=?",
                       (row["job_id"],w,c)).fetchone()
        if not job or job["state"]!="approved":
            raise ValueError("Approve the production job in Approval center first")
    return render_queue.enqueue(w,c,row["job_id"],ids,"fast","preserve","none",[])
