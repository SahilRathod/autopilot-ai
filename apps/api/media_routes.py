"""Loopback-only local media intelligence API, scoped to workspace/channel."""
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from app import media_intelligence as media

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
