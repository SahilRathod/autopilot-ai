"""Explicit creator-approved remote actions. Never retry an ambiguous mutation."""
from datetime import datetime, timezone, timedelta
import hashlib
import re

from app import platform_core as core, youtube_connection as yt
from app import youtube_upload as upload, youtube_insights as insights

_get = insights._get
ID = re.compile(r"[A-Za-z0-9_-]{1,200}")
WRITABLE_STATUS = ("license","embeddable","publicStatsViewable","selfDeclaredMadeForKids","containsSyntheticMedia")


def initialize():
    upload.initialize()
    with core.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS youtube_actions(
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id), remote_channel_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('schedule','reply')), video_id TEXT NOT NULL,
            target_key TEXT NOT NULL, publish_at TEXT, state TEXT NOT NULL
                CHECK(state IN ('requested','confirmed','review_required')),
            provider_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(remote_channel_id,kind,video_id,target_key)
        )""")


def history(w,c):
    initialize()
    yt._link(w,c)
    with core.connect() as db:
        return [dict(row) for row in db.execute("""SELECT id,kind,video_id,publish_at,state,provider_id,
            created_at,updated_at FROM youtube_actions WHERE workspace_id=? AND channel_id=?
            ORDER BY id DESC LIMIT 100""",(w,c))]


def _access(w,c):
    link=yt._link(w,c)
    if not link or not link["manage_authorized"]:
        raise ValueError("Authorize publishing and comment management first")
    remote,access=insights._access(w,c)
    if yt.read_channel(access)["id"]!=remote:
        raise ValueError("Linked channel identity could not be verified")
    return remote,access


def _video(access,remote,video):
    if not ID.fullmatch(video):
        raise ValueError("Invalid video identifier")
    items=insights._items(_get(access,"videos",{"part":"snippet,status","id":video}))
    if len(items)!=1 or items[0].get("id")!=video or items[0].get("snippet",{}).get("channelId")!=remote:
        raise ValueError("Video not found on the linked channel")
    return items[0]


def _mutate(access,method,resource,body,part,etag=None):
    headers={"Authorization":"Bearer "+access}
    if etag:
        headers["If-Match"]=etag
    return yt._json(yt._request(method,insights.API+resource,
                                headers=headers,params={"part":part},json=body))


def _claim(w,c,remote,kind,video,key,publish_at=None):
    initialize()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("""SELECT 1 FROM youtube_links WHERE workspace_id=? AND local_channel_id=?
            AND remote_channel_id=? AND manage_authorized=1""",(w,c,remote)).fetchone():
            raise ValueError("Connection changed; review the action again")
        if db.execute("""SELECT 1 FROM youtube_actions WHERE remote_channel_id=? AND kind=?
            AND video_id=? AND target_key=?""",(remote,kind,video,key)).fetchone():
            raise ValueError("This action was already requested; inspect YouTube Studio instead of repeating it")
        cur=db.execute("""INSERT INTO youtube_actions(workspace_id,channel_id,remote_channel_id,kind,
            video_id,target_key,publish_at,state) VALUES(?,?,?,?,?,?,?,'requested')""",
            (w,c,remote,kind,video,key,publish_at))
        return cur.lastrowid


def _finish(action,state,provider_id=None):
    with core.connect() as db:
        db.execute("""UPDATE youtube_actions SET state=?,provider_id=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",(state,provider_id,action))
        row=db.execute("SELECT * FROM youtube_actions WHERE id=?",(action,)).fetchone()
        db.execute("INSERT INTO audit_log(workspace_id,channel_id,action) VALUES(?,?,?)",
            (row["workspace_id"],row["channel_id"],"youtube_"+row["kind"]+"_"+state))
        return {"id":action,"kind":row["kind"],"video_id":row["video_id"],
                "publish_at":row["publish_at"],"state":state,"provider_id":provider_id}


def _time(value,minimum=True):
    if not isinstance(value,str) or len(value)>64:
        raise ValueError("Provide a timezone-aware publication date")
    try:
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("Provide a timezone-aware publication date") from exc
    if result.tzinfo is None:
        raise ValueError("Provide a timezone-aware publication date")
    result=result.astimezone(timezone.utc).replace(microsecond=0)
    if minimum and result<datetime.now(timezone.utc)+timedelta(hours=1):
        raise ValueError("Choose a publication time at least one hour in the future")
    return result


def schedule(w,c,job,publish_at,approved):
    if approved is not True:
        raise ValueError("Explicit approval to make this video public at the chosen time is required")
    when=_time(publish_at)
    remote,access=_access(w,c)
    initialize()
    with core.connect() as db:
        row=db.execute("""SELECT * FROM youtube_uploads WHERE workspace_id=? AND channel_id=?
            AND job_id=? AND remote_channel_id=? AND state='uploaded'""",(w,c,job,remote)).fetchone()
    if not row or not row["video_id"]:
        raise ValueError("A confirmed private upload from this channel is required")
    video=row["video_id"]
    current=_video(access,remote,video)
    status=current.get("status",{})
    if status.get("privacyStatus")!="private" or status.get("uploadStatus")!="processed" or status.get("publishAt"):
        raise ValueError("Video must be private, processed and not already scheduled")
    if not isinstance(status.get("selfDeclaredMadeForKids"),bool):
        raise ValueError("Review the audience declaration in YouTube Studio first")
    if status["selfDeclaredMadeForKids"] != bool(row["made_for_kids"]):
        raise ValueError("The video's audience declaration changed; review it in YouTube Studio")
    status_update={key:status[key] for key in WRITABLE_STATUS if key in status}
    stamp=when.isoformat()
    status_update.update(privacyStatus="private",publishAt=stamp)
    # Google treats past publishAt as immediate publication. Recheck immediately before the request.
    _time(stamp)
    action=_claim(w,c,remote,"schedule",video,"single-schedule",stamp)
    try:
        result=_mutate(access,"PUT","videos",{"id":video,"status":status_update},"status",current.get("etag"))
        confirmed=result.get("status",{})
        if result.get("id")!=video or confirmed.get("privacyStatus")!="private" or _time(confirmed.get("publishAt"),False)!=when:
            raise RuntimeError("YouTube did not confirm the intended schedule")
        return _finish(action,"confirmed",video)
    except Exception as exc:
        _finish(action,"review_required")
        raise RuntimeError("Schedule outcome requires review in YouTube Studio; do not resend automatically") from exc


def reply(w,c,video,parent,text,approved):
    if approved is not True:
        raise ValueError("Explicit approval to post this exact reply is required")
    if not isinstance(parent,str) or not ID.fullmatch(parent) or not isinstance(text,str) or not 1<=len(text.strip())<=10000:
        raise ValueError("Choose a valid comment and nonempty reply up to 10000 characters")
    remote,access=_access(w,c)
    _video(access,remote,video)
    items=insights._items(_get(access,"comments",{"part":"snippet","id":parent,"textFormat":"plainText"}))
    if len(items)!=1 or items[0].get("id")!=parent:
        raise ValueError("Comment not found")
    snippet=items[0].get("snippet",{})
    if snippet.get("videoId")!=video or snippet.get("parentId"):
        raise ValueError("Choose a top-level comment on the owned video")
    digest=hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    action=_claim(w,c,remote,"reply",video,parent+":"+digest)
    try:
        result=_mutate(access,"POST","comments",{"snippet":{"parentId":parent,"textOriginal":text.strip()}},"snippet")
        if not result.get("id") or result.get("snippet",{}).get("parentId")!=parent:
            raise RuntimeError("YouTube did not confirm the intended reply")
        return _finish(action,"confirmed",result["id"])
    except Exception as exc:
        _finish(action,"review_required")
        raise RuntimeError("Reply outcome requires review in YouTube Studio; do not resend automatically") from exc
