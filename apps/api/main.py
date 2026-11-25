"""V0.3 local-only API. NOT safe to expose on a public network without authentication."""
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import platform_core as core, ai_director, media_intelligence, highlight_ranker, video_assembly, render_queue, youtube_connection, youtube_upload, postproduction, production_operator


@asynccontextmanager
async def lifespan(_app: FastAPI):
    core.initialize()
    ai_director.initialize()
    media_intelligence.initialize()
    highlight_ranker.initialize()
    video_assembly.initialize()
    render_queue.initialize()
    youtube_connection.initialize()
    youtube_upload.initialize()
    postproduction.initialize()
    production_operator.initialize()
    import httpx
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=5.0),
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        follow_redirects=False,
    ) as client:
        _app.state.gemini_client = client
        yield


app = FastAPI(
    title="Autopilot AI Local API", version="0.8.0", lifespan=lifespan,
    description="Local-only management API. Local loopback API; explicit private YouTube uploads supported, public publishing disabled.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Content-Type"],
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class ChannelCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    niche: str = Field(min_length=1, max_length=80)
    language: str = Field(default="Hinglish", min_length=1, max_length=40)


class ChannelUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    niche: str | None = Field(default=None, min_length=1, max_length=80)
    language: str | None = Field(default=None, min_length=1, max_length=40)


class JobCreate(StrictModel):
    channel_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    format: Literal["short", "long"]


class JobTransition(StrictModel):
    to: Literal["ready_for_review", "approved", "rejected", "queued", "completed", "failed"]


def workspace_or_404(workspace_id: int):
    with core.connect() as db:
        row = db.execute("SELECT id, name, created_at FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Workspace not found")
        return dict(row)


def channel_or_404(workspace_id: int, channel_id: int):
    with core.connect() as db:
        row = db.execute("SELECT * FROM channels WHERE workspace_id=? AND id=?", (workspace_id, channel_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Channel not found in this workspace")
        return dict(row)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "0.8.0", "mode": "local", "publishing": False, "private_uploads": True}


@app.get("/api/v1/workspaces")
def workspaces():
    with core.connect() as db:
        return [dict(row) for row in db.execute("SELECT id, name, created_at FROM workspaces ORDER BY id")]


@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(body: WorkspaceCreate):
    return workspace_or_404(core.new_workspace(body.name))


@app.get("/api/v1/workspaces/{workspace_id}/channels")
def channels(workspace_id: int = Path(ge=1)):
    workspace_or_404(workspace_id)
    return core.channels(workspace_id)


@app.post("/api/v1/workspaces/{workspace_id}/channels", status_code=201)
def create_channel(body: ChannelCreate, workspace_id: int = Path(ge=1)):
    workspace_or_404(workspace_id)
    try:
        channel_id = core.new_channel(workspace_id, body.name, body.niche, body.language)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "A channel with that name already exists in this workspace") from exc
    return channel_or_404(workspace_id, channel_id)


@app.patch("/api/v1/workspaces/{workspace_id}/channels/{channel_id}")
def update_channel(body: ChannelUpdate, workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    channel_or_404(workspace_id, channel_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields or any(value is None for value in fields.values()):
        raise HTTPException(422, "Provide non-null channel fields")
    with core.connect() as db:
        try:
            db.execute(
                "UPDATE channels SET " + ", ".join(f"{field}=?" for field in fields) + " WHERE id=? AND workspace_id=?",
                (*fields.values(), channel_id, workspace_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Channel name already exists") from exc
        db.execute(
            "INSERT INTO audit_log(workspace_id,channel_id,action) VALUES(?,?,?)",
            (workspace_id, channel_id, "channel_updated"),
        )
    return channel_or_404(workspace_id, channel_id)


@app.get("/api/v1/workspaces/{workspace_id}/jobs")
def jobs(workspace_id: int = Path(ge=1), channel_id: int | None = Query(default=None, ge=1)):
    workspace_or_404(workspace_id)
    if channel_id is not None:
        channel_or_404(workspace_id, channel_id)
    return core.jobs(workspace_id, channel_id)


@app.post("/api/v1/workspaces/{workspace_id}/jobs", status_code=201)
def create_job(body: JobCreate, workspace_id: int = Path(ge=1)):
    channel_or_404(workspace_id, body.channel_id)
    job_id = core.add_job(workspace_id, body.channel_id, body.title, body.format)
    return next(job for job in core.jobs(workspace_id, body.channel_id) if job["id"] == job_id)


@app.post("/api/v1/workspaces/{workspace_id}/jobs/{job_id}/transition")
def transition_job(body: JobTransition, workspace_id: int = Path(ge=1), job_id: int = Path(ge=1)):
    if not any(job["id"] == job_id for job in core.jobs(workspace_id)):
        raise HTTPException(404, "Job not found in this workspace")
    try:
        core.transition(workspace_id, job_id, body.to)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return next(job for job in core.jobs(workspace_id) if job["id"] == job_id)


@app.get("/api/v1/workspaces/{workspace_id}/audit")
def audit(workspace_id: int = Path(ge=1), limit: int = Query(default=50, ge=1, le=200)):
    workspace_or_404(workspace_id)
    return core.audit(workspace_id)[:limit]


@app.get("/api/v1/workspaces/{workspace_id}/overview")
def overview(workspace_id: int = Path(ge=1)):
    workspace_or_404(workspace_id)
    all_jobs = core.jobs(workspace_id)
    return {
        "workspace_id": workspace_id,
        "channels": len(core.channels(workspace_id)),
        "total_jobs": len(all_jobs),
        "pending_review": sum(job["state"] == "ready_for_review" for job in all_jobs),
        "approved": sum(job["state"] == "approved" for job in all_jobs),
        "queue": sum(job["state"] == "queued" for job in all_jobs),
        "states": {state: sum(job["state"] == state for job in all_jobs) for state in core.STATES},
        "youtube_connected": youtube_connection.workspace_connected(workspace_id),
        "ai_enabled": True, "gemini_configured": ai_director.gemini_enabled(),
        "publishing_enabled": False,
    }


@app.get("/api/v1/workspaces/{workspace_id}/jobs/{job_id}/content")
def job_content(workspace_id: int = Path(ge=1), job_id: int = Path(ge=1)):
    """Read the canonical AI draft for this workspace's production job."""
    with core.connect() as db:
        job = db.execute(
            "SELECT id, channel_id, title, format, state FROM production_jobs "
            "WHERE id=? AND workspace_id=?", (job_id, workspace_id)).fetchone()
        if job is None:
            raise HTTPException(404, "Job not found in this workspace")
        draft = db.execute(
            "SELECT id, topic, provider, result_json FROM ai_drafts "
            "WHERE workspace_id=? AND channel_id=? AND job_id=? LIMIT 1",
            (workspace_id, job["channel_id"], job_id)).fetchone()
        if draft is None:
            raise HTTPException(404, "This job has no AI content pack")
        import json
        return {"job_id": job_id, "channel_id": job["channel_id"],
                "state": job["state"], "draft_id": draft["id"],
                "topic": draft["topic"], "provider": draft["provider"],
                "result": json.loads(draft["result_json"])}


from apps.api.ai_routes import router as ai_router
app.include_router(ai_router)

from apps.api.media_routes import router as media_router
app.include_router(media_router)


from apps.api.youtube_routes import router as youtube_router
app.include_router(youtube_router)


from apps.api.operator_routes import router as operator_router
app.include_router(operator_router)
