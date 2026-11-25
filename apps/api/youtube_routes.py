"""Loopback account and explicit private upload API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app import youtube_connection as yt, youtube_upload as upload

router = APIRouter(prefix="/api/v1", tags=["YouTube accounts"])


class ExplicitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    category_id: str = Field(min_length=1,max_length=3)
    made_for_kids: StrictBool
    private_upload_approved: StrictBool


def local_request(request):
    # Restrict host to local loopback. JSON mutation bodies prevent cross-origin
    # simple-form POSTs; callbacks additionally require an unguessable one-time state.
    if request.url.hostname not in ("127.0.0.1", "localhost"):
        raise HTTPException(403, "Use the local loopback application")
    if request.method == "POST":
        from urllib.parse import urlsplit
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).hostname not in ("127.0.0.1", "localhost"):
            raise HTTPException(403, "Only the local dashboard may initiate this action")


def checked(request, operation, *args):
    local_request(request)
    try:
        return operation(*args)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if "not found" in message.lower() else 409, message) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/workspaces/{w}/channels/{c}/youtube")
def status(request: Request, w: int, c: int):
    return checked(request, yt.status, w, c)


@router.post("/workspaces/{w}/channels/{c}/youtube/connect")
def connect(request: Request, w: int, c: int, body: ExplicitRequest):
    return checked(request, yt.begin, w, c)


@router.post("/workspaces/{w}/channels/{c}/youtube/refresh")
def refresh(request: Request, w: int, c: int, body: ExplicitRequest):
    return checked(request, yt.refresh, w, c)


@router.post("/workspaces/{w}/channels/{c}/youtube/disconnect")
def disconnect(request: Request, w: int, c: int, body: ExplicitRequest):
    return checked(request, yt.disconnect, w, c)


@router.post("/workspaces/{w}/channels/{c}/youtube/forget")
def forget(request: Request, w: int, c: int, body: ExplicitRequest):
    return checked(request, yt.forget_local, w, c)


@router.get("/youtube/callback", response_class=HTMLResponse)
def callback(request: Request, state: str = "", code: str = "", error: str = ""):
    local_request(request)
    # Do not echo provider query parameters, codes, tokens or detailed errors.
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
               "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"}
    try:
        yt.finish(state, "" if error else code)
    except (ValueError, RuntimeError):
        return HTMLResponse("<h1>Connection not completed</h1><p>Return to Autopilot AI and start a new authorization. Check API access and channel selection.</p>",
                            status_code=400, headers=headers)
    return HTMLResponse("<h1>Connection successful</h1><p>Return to Autopilot AI, then refresh your channel information. You may close this tab.</p>",
                        headers=headers)


@router.post("/workspaces/{w}/channels/{c}/youtube/authorize-upload")
def authorize_upload(request: Request, w: int, c: int, body: ExplicitRequest):
    return checked(request, yt.begin, w, c, True)


@router.get("/workspaces/{w}/channels/{c}/youtube/uploads")
def list_uploads(request: Request, w: int, c: int):
    return checked(request, upload.tasks, w, c)


@router.post("/workspaces/{w}/channels/{c}/youtube/uploads",status_code=202)
def queue_upload(request: Request, w: int, c: int, body: PrivateUploadRequest):
    return checked(request, upload.enqueue,w,c,body.job_id,body.title,body.description,
                   body.category_id,body.made_for_kids,body.private_upload_approved)


@router.post("/workspaces/{w}/channels/{c}/youtube/uploads/{job}/retry",status_code=202)
def retry_upload(request: Request, w: int, c: int, job: int, body: ExplicitRequest):
    return checked(request, upload.retry,w,c,job)


@router.post("/workspaces/{w}/channels/{c}/youtube/uploads/{job}/cancel")
def cancel_upload(request: Request, w: int, c: int, job: int, body: ExplicitRequest):
    return checked(request,upload.cancel,w,c,job)
