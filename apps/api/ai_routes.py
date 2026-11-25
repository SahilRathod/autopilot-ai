"""V0.4 AI Director API. Keep loopback-only until authentication exists."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from app import ai_director as ai

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/channels/{channel_id}/ai", tags=["AI Director"])

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Generate(Strict):
    topic: str = Field(min_length=3, max_length=180)
    format: Literal["short", "long"] = "short"
    provider: Literal["offline", "gemini"] = "offline"
    refresh: bool = False

class Memory(Strict):
    value: str = Field(min_length=1, max_length=500)

def safe(fn, *args):
    try: return fn(*args)
    except ValueError as e: raise HTTPException(status_code=404, detail=str(e)) from e

@router.get("/status")
def status(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    safe(ai.channel,workspace_id,channel_id)
    return {"offline_ready":True,"gemini_configured":ai.gemini_enabled(),"model":ai.MODEL,"publishing":False}

@router.get("/memory")
def memory(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    return safe(ai.memory,workspace_id,channel_id)

@router.put("/memory/{key}")
def remember(body: Memory, workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1), key: str = Path(max_length=40)):
    try: ai.remember(workspace_id,channel_id,key,body.value)
    except ValueError as e: raise HTTPException(status_code=422,detail=str(e)) from e
    return {"key":key,"value":body.value}

@router.post("/generate",status_code=201)
async def generate(body: Generate, request: Request, workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1)):
    try:
        return await ai.generate(workspace_id,channel_id,body.topic,body.format,body.provider,
                                 body.refresh,request.app.state.gemini_client)
    except ValueError as e: raise HTTPException(status_code=404,detail=str(e)) from e
    except ai.AIError as e: raise HTTPException(status_code=503,detail=str(e)) from e

@router.get("/drafts")
def drafts(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1), limit: int = Query(default=30,ge=1,le=100)):
    return safe(ai.drafts,workspace_id,channel_id)[:limit]

@router.post("/drafts/{draft_id}/submit")
def submit(workspace_id: int = Path(ge=1), channel_id: int = Path(ge=1), draft_id: int = Path(ge=1)):
    return {"job_id":safe(ai.submit,workspace_id,channel_id,draft_id),"status":"draft","published":False}


class EditDraft(Strict):
    title: str = Field(min_length=1,max_length=100)
    hook: str = Field(min_length=1,max_length=1000)
    script: str = Field(min_length=1,max_length=12000)
    description: str = Field(min_length=1,max_length=5000)


@router.put("/drafts/{draft_id}")
def edit_draft(body: EditDraft,workspace_id: int = Path(ge=1),channel_id: int = Path(ge=1),draft_id: int = Path(ge=1)):
    try:
        return ai.edit_draft(workspace_id,channel_id,draft_id,body.title,body.hook,body.script,body.description)
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 409,str(exc)) from exc
