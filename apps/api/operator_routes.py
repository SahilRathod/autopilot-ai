"""Scheduled local operator API."""
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from app import production_operator as op
router=APIRouter(prefix="/api/v1/workspaces/{w}/channels/{c}/operator",tags=["Content planner"])

class Schedule(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    topic: str = Field(min_length=3,max_length=180)
    format: Literal["short","long"]="short"
    due_at: str|None=None
    asset_id: int|None=Field(default=None,ge=1)
    clip_seconds: float=Field(default=30,ge=1,le=120,allow_inf_nan=False)
    scan_seconds: float=Field(default=120,ge=2,le=600,allow_inf_nan=False)
    profile: Literal["balanced","tactical","sandbox"]="balanced"

def checked(fn,*args):
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 409,str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc

@router.get("/tasks")
def tasks(w:int,c:int):
    return checked(op.tasks,w,c)

@router.post("/tasks",status_code=201)
def schedule(body:Schedule,w:int,c:int):
    return checked(op.schedule,w,c,body.topic,body.format,body.due_at,body.asset_id,
                   body.clip_seconds,body.scan_seconds,body.profile)

@router.post("/tasks/{task}/cancel")
def cancel(w:int,c:int,task:int):
    return checked(op.cancel,w,c,task)

@router.post("/tasks/{task}/retry")
def retry(w:int,c:int,task:int):
    return checked(op.retry,w,c,task)

@router.post("/tasks/{task}/render",status_code=202)
def render(w:int,c:int,task:int):
    return checked(op.queue_recommended,w,c,task)
