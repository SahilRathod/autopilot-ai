"""Loopback-only local media intelligence API, scoped to workspace/channel."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app import media_intelligence as media, highlight_ranker as ranker, video_assembly as assembly, render_queue as queue, postproduction as post

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/channels/{channel_id}/media",
                   tags=["V0.5 Media Intelligence"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Import(Strict):
    filename: str = Field(min_length=1, max_length=255)


class Scan(Strict):
    clip_seconds: float = Field(default=30, ge=1, le=120, allow_inf_nan=False)
    threshold: float = Field(default=0.35, ge=0.05, le=0.95, allow_inf_nan=False)
    max_scan_seconds: float = Field(default=120, ge=2, le=600, allow_inf_nan=False)




class RankingRequest(Strict):
    profile: Literal["balanced", "tactical", "sandbox"] = "balanced"
    max_seconds: float = Field(default=120, gt=0, le=600, allow_inf_nan=False)

class AssemblyCreate(Strict):
    job_id: int = Field(ge=1)
    candidate_ids: list[int] = Field(min_length=1, max_length=8)
    quality: Literal["fast", "high"] = "fast"
    audio_mode: Literal["preserve", "normalize", "mute"] = "preserve"
    caption_mode: Literal["none", "soft", "burn"] = "none"
    caption_lines: list[str] = Field(default_factory=list, max_length=40)


class Render(Strict):
    job_id: int = Field(ge=1)


def checked(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        # Invalid source paths, missing records, source changes, or bad parameters
        raise HTTPException(422 if "Invalid" in str(exc) or "filename" in str(exc).lower()
                            or "Use an existing video" in str(exc)
                            else 404 if "not found" in str(exc).lower() else 409,
                            detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail=str(exc)) from exc


@router.post("/import", status_code=201)
def import_media(body: Import, workspace_id: int = Path(ge=1),
                 channel_id: int = Path(ge=1)):
    return checked(media.import_media, workspace_id, channel_id, body.filename)


@router.get("/assets")
def assets(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    return checked(media.assets, workspace_id, channel_id)


@router.get("/assets/{asset_id}")
def asset(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1),
          asset_id: int = Path(ge=1)):
    return checked(media.asset, workspace_id, channel_id, asset_id)


@router.post("/assets/{asset_id}/scan")
def scan_media(body: Scan, workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1),
               asset_id: int = Path(ge=1)):
    return checked(media.scan_media, workspace_id, channel_id, asset_id,
                   body.clip_seconds, body.threshold, body.max_scan_seconds)


@router.get("/assets/{asset_id}/candidates")
def candidates(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1),
               asset_id: int = Path(ge=1)):
    return checked(media.candidates, workspace_id, channel_id, asset_id)


@router.post("/candidates/{candidate_id}/render")
def render_candidate(body: Render, workspace_id: int = Path(ge=1),
                     channel_id: int = Path(ge=1), candidate_id: int = Path(ge=1)):
    # Explicit API action only; never triggered by a scene scan itself.
    return checked(media.render_candidate, workspace_id, channel_id, candidate_id, body.job_id)


@router.get("/assets/{asset_id}/preview")
def preview_asset(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1),
                  asset_id: int = Path(ge=1)):
    """Serve only the registered original for this channel; Starlette handles byte ranges."""
    record = checked(media.asset, workspace_id, channel_id, asset_id)
    try:
        source = media.preview_source(record)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(409, detail="Imported media has changed or is missing; import again") from exc
    # Browser playback is not guaranteed for other video containers/codecs.
    if source.suffix.lower() not in (".mp4", ".webm"):
        raise HTTPException(415, detail="Browser preview supports MP4 or WebM containers only")
    mime = "video/mp4" if source.suffix.lower() == ".mp4" else "video/webm"
    return FileResponse(
        source, media_type=mime,
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff",
                 "Accept-Ranges": "bytes"},
    )


@router.post("/assets/{asset_id}/rank")
def rank_candidates(body: RankingRequest, workspace_id: int = Path(ge=1),
                    channel_id: int = Path(ge=1), asset_id: int = Path(ge=1)):
    """Compute local audio/visual heuristic rankings. Does NOT detect game events."""
    return checked(ranker.rank_asset, workspace_id, channel_id, asset_id,
                   body.profile, body.max_seconds)


@router.get("/assets/{asset_id}/rankings")
def get_rankings(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1),
                 asset_id: int = Path(ge=1),
                 profile: Literal["balanced", "tactical", "sandbox"] = Query(default="balanced")):
    return checked(ranker.rankings, workspace_id, channel_id, asset_id, profile)



@router.post("/assemble", status_code=201)
def assemble_export(body: AssemblyCreate, workspace_id: int = Path(ge=1),
                    channel_id: int = Path(ge=1)):
    """Explicit local render request for an approved job; never uploads externally."""
    return checked(assembly.export_job, workspace_id, channel_id,
                   body.job_id, body.candidate_ids, body.quality,
                   body.audio_mode, body.caption_mode, body.caption_lines)


@router.get("/exports")
def assembled_exports(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    return checked(assembly.exports, workspace_id, channel_id)


@router.get("/exports/{job_id}/preview")
def preview_assembled_export(workspace_id: int = Path(ge=1),
                             channel_id: int = Path(ge=1),
                             job_id: int = Path(ge=1)):
    """Range-enabled local preview, limited to finished, channel-scoped MP4s."""
    source = checked(assembly.export_file, workspace_id, channel_id, job_id)
    return FileResponse(
        source, media_type="video/mp4",
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes"},
    )


@router.post("/render-tasks", status_code=202)
def enqueue_render(body: AssemblyCreate, workspace_id: int = Path(ge=1),
                   channel_id: int = Path(ge=1)):
    return checked(queue.enqueue, workspace_id, channel_id, body.job_id,
                   body.candidate_ids, body.quality, body.audio_mode,
                   body.caption_mode, body.caption_lines)


@router.get("/render-tasks")
def render_tasks(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    return checked(queue.list_tasks, workspace_id, channel_id)


@router.post("/render-tasks/{job_id}/retry", status_code=202)
def retry_render(job_id: int = Path(ge=1), workspace_id: int = Path(ge=1),
                 channel_id: int = Path(ge=1)):
    return checked(queue.retry, workspace_id, channel_id, job_id)


class TimedCaptionRequest(Strict):
    srt: str = Field(min_length=1,max_length=131072)


class NarrationRequest(Strict):
    filename: str = Field(min_length=1,max_length=255)
    game_volume: float = Field(default=0.25,ge=0,le=2,allow_inf_nan=False)
    voice_volume: float = Field(default=1,gt=0,le=2,allow_inf_nan=False)


class ThumbnailRequest(Strict):
    timestamp: float = Field(ge=0,allow_inf_nan=False)


@router.get("/exports/{job_id}/revisions")
def revisions(workspace_id: int,channel_id: int,job_id: int):
    return checked(post.history,workspace_id,channel_id,job_id)


@router.post("/exports/{job_id}/captions",status_code=201)
def timed_captions(body: TimedCaptionRequest,workspace_id: int,channel_id: int,job_id: int):
    return checked(post.attach_captions,workspace_id,channel_id,job_id,body.srt)


@router.post("/exports/{job_id}/narration",status_code=201)
def narration(body: NarrationRequest,workspace_id: int,channel_id: int,job_id: int):
    return checked(post.mix_voiceover,workspace_id,channel_id,job_id,body.filename,body.game_volume,body.voice_volume)


@router.post("/exports/{job_id}/revisions/{revision_id}/activate")
def activate_revision(workspace_id: int,channel_id: int,job_id: int,revision_id: int):
    return checked(post.activate_revision,workspace_id,channel_id,job_id,revision_id)


@router.post("/exports/{job_id}/thumbnail",status_code=201)
def create_thumbnail(body: ThumbnailRequest,workspace_id: int,channel_id: int,job_id: int):
    return checked(post.create_thumbnail,workspace_id,channel_id,job_id,body.timestamp)


@router.get("/exports/{job_id}/thumbnail")
def thumbnail(workspace_id: int,channel_id: int,job_id: int):
    path=checked(post.thumbnail_file,workspace_id,channel_id,job_id)
    return FileResponse(path,media_type="image/jpeg",headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
