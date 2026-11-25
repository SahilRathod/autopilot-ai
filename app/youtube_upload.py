"""Explicit private YouTube uploads using durable resumable sessions.

No automatic public publishing. Ambiguous session expiry requires human review.
"""
import argparse
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx

from app import platform_core as core, video_assembly as assembly, youtube_connection as yt
from app.render_queue import worker_lock

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK = 8 * 1024 * 1024


class ReviewRequired(RuntimeError):
    pass


def initialize():
    yt.initialize()
    assembly.initialize()
    with core.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS youtube_uploads (
            job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id),
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            remote_channel_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('pending','uploading','uploaded','failed','interrupted','review_required')),
            title TEXT NOT NULL, description TEXT NOT NULL, category_id TEXT NOT NULL,
            made_for_kids INTEGER NOT NULL,
            file_sha256 TEXT NOT NULL, file_bytes INTEGER NOT NULL,
            encrypted_session BLOB, bytes_uploaded INTEGER NOT NULL DEFAULT 0,
            video_id TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_youtube_uploads_state ON youtube_uploads(state,created_at)")


def _public(row):
    return {k: row[k] for k in ("job_id","workspace_id","channel_id","remote_channel_id",
        "state","title","file_bytes","bytes_uploaded","video_id","error","attempts","created_at","updated_at")}


def tasks(w,c):
    yt._link(w,c)
    initialize()
    with core.connect() as db:
        return [_public(r) for r in db.execute("""SELECT * FROM youtube_uploads WHERE workspace_id=?
            AND channel_id=? ORDER BY created_at DESC,job_id DESC LIMIT 100""",(w,c))]


def _fingerprint(path):
    before=path.stat()
    with path.open("rb") as f:
        digest=hashlib.file_digest(f,"sha256").hexdigest()
    after=path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("Export changed while being checked")
    if after.st_size <= 0:
        raise ValueError("Export file is empty")
    return digest,after.st_size,after.st_mtime_ns


def _export(w,c,job):
    path=assembly.export_file(w,c,job)
    with core.connect() as db:
        row=db.execute("""SELECT a.*,j.format,j.state AS job_state FROM assembly_exports a
            JOIN production_jobs j ON j.id=a.job_id WHERE a.job_id=? AND a.workspace_id=?
            AND a.channel_id=? AND a.state='ready'""",(job,w,c)).fetchone()
    if not row or row["job_state"] not in ("approved","completed"):
        raise ValueError("Only an approved, finished local export can be uploaded")
    return path,row


def enqueue(w,c,job,title,description,category_id,made_for_kids,consent):
    initialize()
    if consent is not True:
        raise ValueError("Explicit private upload approval is required")
    if not isinstance(made_for_kids,bool):
        raise ValueError("Select whether the video is made for kids")
    if not isinstance(title,str) or not title.strip() or len(title.strip())>100 or any(ch in title for ch in "<>"):
        raise ValueError("YouTube title must be 1–100 characters without angle brackets")
    if not isinstance(description,str) or len(description.encode("utf-8"))>5000 or any(ch in description for ch in "<>"):
        raise ValueError("Description must fit 5000 UTF-8 bytes without angle brackets")
    if not isinstance(category_id,str) or not re.fullmatch(r"[0-9]{1,3}",category_id):
        raise ValueError("Choose a valid YouTube category")
    link=yt._link(w,c)
    if not link or not link["upload_authorized"]:
        raise ValueError("Authorize YouTube uploads for this channel first")
    path,export=_export(w,c,job)
    assembly.validate_output(path,export["format"],export["quality"],export["caption_mode"],export["total_seconds"])
    digest,size,_=_fingerprint(path)
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current=db.execute("""SELECT 1 FROM youtube_links WHERE local_channel_id=? AND workspace_id=?
            AND remote_channel_id=? AND upload_authorized=1""",(c,w,link["remote_channel_id"])).fetchone()
        if not current:
            raise ValueError("YouTube authorization changed; review and approve again")
        if db.execute("SELECT 1 FROM youtube_uploads WHERE job_id=?",(job,)).fetchone():
            raise ValueError("This job already has an upload record")
        db.execute("""INSERT INTO youtube_uploads
            (job_id,workspace_id,channel_id,remote_channel_id,state,title,description,category_id,made_for_kids,file_sha256,file_bytes)
            VALUES(?,?,?,?,'pending',?,?,?,?,?,?)""",
            (job,w,c,link["remote_channel_id"],title.strip(),description,category_id,int(made_for_kids),digest,size))
        db.execute("""INSERT INTO audit_log(workspace_id,channel_id,job_id,action)
            VALUES(?,?,?,'youtube_private_upload_approved')""",(w,c,job))
        return _public(db.execute("SELECT * FROM youtube_uploads WHERE job_id=?",(job,)).fetchone())


def retry(w,c,job):
    initialize()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM youtube_uploads WHERE job_id=? AND workspace_id=? AND channel_id=?",(job,w,c)).fetchone()
        if not row or row["state"] not in ("failed","interrupted"):
            raise ValueError("Only failed or interrupted uploads can be retried")
        link=db.execute("""SELECT 1 FROM youtube_links WHERE local_channel_id=? AND workspace_id=?
            AND remote_channel_id=? AND upload_authorized=1""",(c,w,row["remote_channel_id"])).fetchone()
        if not link:
            raise ValueError("Reconnect the original YouTube channel before retrying")
        db.execute("UPDATE youtube_uploads SET state='pending',error=NULL,updated_at=CURRENT_TIMESTAMP WHERE job_id=?",(job,))
        return _public(db.execute("SELECT * FROM youtube_uploads WHERE job_id=?",(job,)).fetchone())


def validate_session(url):
    parsed=urlsplit(url)
    if (parsed.scheme!="https" or parsed.netloc not in ("www.googleapis.com","youtube.googleapis.com")
            or parsed.path!="/upload/youtube/v3/videos" or not parse_qs(parsed.query).get("upload_id")
            or parsed.fragment):
        raise ValueError("Google returned an invalid upload session")
    return url


def _http(method,url,access,**kwargs):
    try:
        headers={"Authorization":"Bearer "+access} | kwargs.pop("headers",{})
        with httpx.Client(timeout=httpx.Timeout(120,connect=10),follow_redirects=False) as client:
            return client.request(method,url,headers=headers,**kwargs)
    except httpx.HTTPError as exc:
        # Never include resumable URL or credentials in logs or status.
        raise RuntimeError("YouTube upload network request failed; retry the existing session") from exc


def initiate(row,access):
    response=_http("POST",UPLOAD_URL,access,
        params={"part":"snippet,status","uploadType":"resumable","notifySubscribers":"false"},
        headers={"X-Upload-Content-Type":"video/mp4","X-Upload-Content-Length":str(row["file_bytes"])},
        json={"snippet":{"title":row["title"],"description":row["description"],"categoryId":row["category_id"]},
              "status":{"privacyStatus":"private","selfDeclaredMadeForKids":bool(row["made_for_kids"])}})
    if not response.is_success or not response.headers.get("Location"):
        raise RuntimeError(f"Could not initiate private upload (HTTP {response.status_code})")
    return validate_session(response.headers["Location"])


def query_session(session,access,total):
    return _http("PUT",validate_session(session),access,
                 headers={"Content-Length":"0","Content-Range":f"bytes */{total}"},content=b"")


def send_chunk(session,access,data,offset,total):
    return _http("PUT",validate_session(session),access,content=data,
        headers={"Content-Type":"video/mp4","Content-Length":str(len(data)),
                 "Content-Range":f"bytes {offset}-{offset+len(data)-1}/{total}"})


def next_offset(response,total):
    value=response.headers.get("Range")
    if not value:
        return 0
    m=re.fullmatch(r"bytes=0-([0-9]+)",value)
    if not m or not 0<=int(m[1])<total:
        raise ValueError("Invalid YouTube upload range")
    return int(m[1])+1


def verify_result(result,remote):
    identifier=result.get("id")
    if (not isinstance(identifier,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",identifier)
            or result.get("snippet",{}).get("channelId")!=remote
            or result.get("status",{}).get("privacyStatus")!="private"):
        raise ValueError("Upload response did not confirm the intended private channel video")
    return identifier


def _update(job,**fields):
    # Field names are supplied only by internal callers.
    fields["updated_at"]=None
    assignments=",".join(k+"=CURRENT_TIMESTAMP" if k=="updated_at" else k+"=?" for k in fields)
    values=[v for k,v in fields.items() if k!="updated_at"]
    with core.connect() as db:
        db.execute("UPDATE youtube_uploads SET "+assignments+" WHERE job_id=?",(*values,job))
        return _public(db.execute("SELECT * FROM youtube_uploads WHERE job_id=?",(job,)).fetchone())


def _linked(row):
    link=yt._link(row["workspace_id"],row["channel_id"])
    if not link or not link["upload_authorized"] or link["remote_channel_id"]!=row["remote_channel_id"]:
        raise ValueError("Original YouTube upload authorization is no longer available")
    return link


def _response(response,row):
    if response.status_code in (200,201):
        try:
            identifier=verify_result(response.json(),row["remote_channel_id"])
        except (ValueError,TypeError,AttributeError) as exc:
            raise ReviewRequired("Google may have received the video; verify YouTube Studio before any new upload") from exc
        with core.connect() as db:
            db.execute("""UPDATE youtube_uploads SET state='uploaded',video_id=?,bytes_uploaded=file_bytes,
                encrypted_session=NULL,error=NULL,updated_at=CURRENT_TIMESTAMP WHERE job_id=?""",(identifier,row["job_id"]))
            db.execute("""INSERT INTO audit_log(workspace_id,channel_id,job_id,action,detail)
                VALUES(?,?,?,'youtube_private_uploaded',?)""",(row["workspace_id"],row["channel_id"],row["job_id"],identifier))
            return _public(db.execute("SELECT * FROM youtube_uploads WHERE job_id=?",(row["job_id"],)).fetchone())
    if response.status_code in (404,410):
        raise ReviewRequired("Upload session expired or is unknown. Check YouTube Studio; no second upload will be started.")
    if response.status_code!=308:
        raise RuntimeError(f"YouTube upload request failed (HTTP {response.status_code}); retry same session")
    try:
        offset=next_offset(response,row["file_bytes"])
    except ValueError as exc:
        raise ReviewRequired("Google returned an invalid upload range; verify YouTube Studio") from exc
    _update(row["job_id"],bytes_uploaded=offset)
    return offset


def _execute(row):
    job=row["job_id"]
    path,_=_export(row["workspace_id"],row["channel_id"],job)
    digest,total,mtime=_fingerprint(path)
    if digest!=row["file_sha256"] or total!=row["file_bytes"]:
        raise ValueError("Export changed since private upload approval")
    link=_linked(row)
    client=yt.config()
    if client["client_id"]!=link["client_id"]:
        raise ValueError("Use original OAuth client configuration")
    access=yt.refresh_access(yt.unprotect(link["encrypted_refresh"]),client)
    if yt.read_channel(access)["id"]!=row["remote_channel_id"]:
        raise ValueError("Authorized channel does not match reviewed upload")
    if row["encrypted_session"]:
        session=validate_session(yt.unprotect(row["encrypted_session"]))
        result=_response(query_session(session,access,total),row)
        if isinstance(result,dict):
            return result
        offset=result
    else:
        session=initiate(row,access)
        _update(job,encrypted_session=yt.protect(session))
        offset=0
    with path.open("rb") as source:
        while offset<total:
            _linked(row)  # respect revoked local authorization between chunks
            stat=path.stat()
            if stat.st_size!=total or stat.st_mtime_ns!=mtime:
                raise ReviewRequired("Export changed during transfer; check YouTube Studio")
            source.seek(offset)
            data=source.read(min(CHUNK,total-offset))
            if not data:
                raise ReviewRequired("Export became unreadable during transfer")
            result=_response(send_chunk(session,access,data,offset,total),row)
            if isinstance(result,dict):
                return result
            if result<=offset or result>offset+len(data):
                raise RuntimeError("YouTube acknowledged an unexpected offset; retry same session")
            offset=result
    raise ReviewRequired("All bytes acknowledged without final video ID; check YouTube Studio")


def run_once():
    initialize()
    with worker_lock(".upload-worker.lock"):
        with core.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE youtube_uploads SET state='interrupted',
                error='Upload worker stopped; retry resumes the same session',updated_at=CURRENT_TIMESTAMP
                WHERE state='uploading'""")
            row=db.execute("SELECT * FROM youtube_uploads WHERE state='pending' ORDER BY created_at,job_id LIMIT 1").fetchone()
            if not row:
                return None
            job=row["job_id"]
            db.execute("""UPDATE youtube_uploads SET state='uploading',attempts=attempts+1,
                updated_at=CURRENT_TIMESTAMP WHERE job_id=?""",(job,))
        try:
            return _execute(row)
        except ReviewRequired as exc:
            return _update(job,state="review_required",error=str(exc))
        except Exception as exc:
            # No arbitrary exception text: it can include a bearer session URL.
            with core.connect() as db:
                saved=db.execute("SELECT encrypted_session FROM youtube_uploads WHERE job_id=?",(job,)).fetchone()
            state="interrupted" if saved and saved["encrypted_session"] else "failed"
            reason=str(exc) if isinstance(exc,(ValueError,RuntimeError)) and not isinstance(exc,httpx.HTTPError) else "Upload failed; review local configuration"
            # Internal known errors are sanitized; protect against unexpected third-party URL strings.
            if "http://" in reason or "https://" in reason:
                reason="Upload failed; review local configuration"
            return _update(job,state=state,error=reason[:400])


def main():
    parser=argparse.ArgumentParser(description="Local private YouTube upload worker")
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    core.initialize()
    while True:
        try:
            result=run_once()
            if result:
                print(f"Upload job {result['job_id']}: {result['state']}",flush=True)
            if args.once:
                return
            if result is None:
                time.sleep(3)
        except KeyboardInterrupt:
            return
        except RuntimeError as exc:
            parser.exit(1,str(exc)+"\n")


if __name__=="__main__":
    main()
