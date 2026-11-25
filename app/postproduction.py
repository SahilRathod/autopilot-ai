"""Local finishing tools: timed captions, narration mix, thumbnails, immutable revisions."""
import argparse
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from app import editor, platform_core as core, video_assembly as assembly, youtube_upload


def initialize():
    youtube_upload.initialize()
    with core.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS export_revisions(
            id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES production_jobs(id),
            output_path TEXT NOT NULL, caption_mode TEXT NOT NULL, operation TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(job_id,output_path))""")
        db.execute("""CREATE TABLE IF NOT EXISTS export_thumbnails(
            job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id),
            output_path TEXT NOT NULL, timestamp_seconds REAL NOT NULL,
            source_output TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")


def _row(w,c,job):
    initialize()
    path,row=youtube_upload._export(w,c,job)
    return path,row


def _check_unsubmitted(db,job):
    if db.execute("SELECT 1 FROM youtube_uploads WHERE job_id=?",(job,)).fetchone():
        raise ValueError("An upload record exists; create a new reviewed job to revise this video")


def _milliseconds(text):
    m=re.fullmatch(r"(\d{2}):([0-5]\d):([0-5]\d),(\d{3})",text)
    if not m:
        raise ValueError("Use SRT timestamps HH:MM:SS,mmm")
    h,mn,s,ms=map(int,m.groups())
    return ((h*60+mn)*60+s)*1000+ms


def parse_srt(value,duration):
    if not isinstance(value,str) or len(value.encode("utf-8"))>128*1024 or not math.isfinite(duration) or duration<=0:
        raise ValueError("Invalid SRT size or video duration")
    value=value.lstrip("\ufeff").replace("\r\n","\n").replace("\r","\n").strip()
    blocks=re.split(r"\n[ \t]*\n",value)
    if not value or len(blocks)>1000:
        raise ValueError("Supply 1–1000 timed caption cues")
    cues=[]; previous=0
    for index,block in enumerate(blocks,1):
        lines=block.splitlines()
        if len(lines)<3 or lines[0].strip()!=str(index):
            raise ValueError("Use sequential SRT cue numbers")
        times=lines[1].strip().split(" --> ")
        if len(times)!=2:
            raise ValueError("Invalid SRT timing line")
        start,end=map(_milliseconds,times)
        if start<previous or end<=start or end>round(duration*1000)+100:
            raise ValueError("Caption times must be ordered, non-overlapping and within the video")
        text="\n".join(line.strip() for line in lines[2:]).strip()
        if (not text or len(text)>400 or "<" in text or ">" in text or "{" in text or "}" in text
                or any(ord(ch)<32 and ch!="\n" for ch in text)):
            raise ValueError("Captions must contain plain text of at most 400 characters per cue")
        cues.append((start/1000,end/1000,text));previous=end
    return cues


def to_srt(cues):
    return "\n\n".join(f"{i}\n{assembly._srt_time(start)} --> {assembly._srt_time(end)}\n{text}"
                       for i,(start,end,text) in enumerate(cues,1))+"\n"


def _ffmpeg(args,timeout=300,cwd=None):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg not available")
    try:
        subprocess.run(["ffmpeg","-nostdin","-y","-hide_banner","-loglevel","error",*args],
                       cwd=cwd,check=True,timeout=timeout,capture_output=True)
    except (subprocess.SubprocessError,OSError) as exc:
        raise RuntimeError("FFmpeg finishing step failed; check input format and disk space") from exc


def mux_captions(source,target,srt):
    with tempfile.TemporaryDirectory(prefix=".captions-",dir=editor.OUT) as temp:
        caption=Path(temp)/"timed.srt"
        caption.write_text(srt,encoding="utf-8")
        _ffmpeg(["-i",str(source),"-i",str(caption),"-map","0:v:0","-map","0:a:0","-map","1:0",
                 "-c:v","copy","-c:a","copy","-c:s","mov_text","-movflags","+faststart",str(target)])


def _revision(w,c,job,operation,caption_mode,process,expected_output):
    source,row=_row(w,c,job)
    if row['output_path']!=expected_output:
        raise ValueError('Export version changed; reload before editing')
    with core.connect() as db:
        _check_unsubmitted(db,job)
    target=editor.OUT/f"revision_{job}_{uuid.uuid4().hex[:12]}.mp4"
    before=source.stat()
    try:
        with tempfile.TemporaryDirectory(prefix=".revision-",dir=editor.OUT) as scratch:
            staged=Path(scratch)/"output.mp4"
            process(source,staged)
            assembly.validate_output(staged,row["format"],row["quality"],caption_mode,row["total_seconds"])
            after=source.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError("Original export changed during finishing")
            os.replace(staged,target)
        with core.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _check_unsubmitted(db,job)
            active=db.execute("""SELECT output_path FROM assembly_exports WHERE job_id=? AND workspace_id=?
                    AND channel_id=? AND state='ready'""",(job,w,c)).fetchone()
            if not active or active["output_path"]!=row["output_path"]:
                raise ValueError("Export changed; reload the latest version before editing")
            db.execute("""INSERT OR IGNORE INTO export_revisions(job_id,output_path,caption_mode,operation)
                          VALUES(?,?,?,'original')""",(job,row["output_path"],row["caption_mode"]))
            db.execute("""INSERT INTO export_revisions(job_id,output_path,caption_mode,operation)
                          VALUES(?,?,?,?)""",(job,str(target),caption_mode,operation))
            db.execute("""UPDATE assembly_exports SET output_path=?,caption_mode=? WHERE job_id=?""",
                       (str(target),caption_mode,job))
            db.execute("""INSERT INTO audit_log(workspace_id,channel_id,job_id,action,detail)
                          VALUES(?,?,?,'export_revised',?)""",(w,c,job,operation))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"job_id":job,"output_path":str(target),"caption_mode":caption_mode,"operation":operation}


def attach_captions(w,c,job,srt):
    _,row=_row(w,c,job)
    if row["caption_mode"]=="burn":
        raise ValueError("Burned-in text cannot be removed; use a clean export")
    normalized=to_srt(parse_srt(srt,row["total_seconds"]))
    return _revision(w,c,job,"timed_captions","soft",
                     lambda source,target:mux_captions(source,target,normalized),row['output_path'])


def _voice_file(filename):
    if not isinstance(filename,str) or Path(filename).name!=filename:
        raise ValueError("Use a narration audio filename from media/raw")
    path=(editor.RAW/filename).resolve()
    if path.parent!=editor.RAW.resolve() or not path.is_file() or path.suffix.lower() not in (
            ".wav",".mp3",".m4a",".aac",".ogg",".flac"):
        raise ValueError("Use an existing narration audio file in media/raw")
    return path


def mix_voiceover(w,c,job,filename,game_volume=0.25,voice_volume=1.0):
    _,row=_row(w,c,job)
    audio=_voice_file(filename)
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and 0<=x<=2 for x in (game_volume,voice_volume)):
        raise ValueError("Volume must be between 0 and 2")
    if voice_volume<=0:
        raise ValueError("Narration volume must be greater than zero")
    def process(source,target):
        filters=(f"[0:a:0]volume={game_volume}[game];[1:a:0]volume={voice_volume},apad[voice];"
                 "[game][voice]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]")
        _ffmpeg(["-i",str(source),"-i",str(audio),"-filter_complex",filters,
                 "-map","0:v:0","-map","[mix]","-map","0:s?","-c:v","copy","-c:a","aac",
                 "-b:a","192k","-c:s","copy","-movflags","+faststart",str(target)])
    return _revision(w,c,job,"narration_mix",row["caption_mode"],process,row["output_path"])


def history(w,c,job):
    path,row=_row(w,c,job)
    with core.connect() as db:
        versions=db.execute("SELECT * FROM export_revisions WHERE job_id=? ORDER BY id DESC",(job,)).fetchall()
    if not versions:
        return [{"id":0,"operation":"original","caption_mode":row["caption_mode"],"active":True}]
    return [{"id":v["id"],"operation":v["operation"],"caption_mode":v["caption_mode"],
             "created_at":v["created_at"],"active":v["output_path"]==row["output_path"]} for v in versions]


def activate_revision(w,c,job,revision_id):
    _row(w,c,job)
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _check_unsubmitted(db,job)
        version=db.execute("SELECT * FROM export_revisions WHERE id=? AND job_id=?",(revision_id,job)).fetchone()
        if not version:
            raise ValueError("Revision not found")
        path=Path(version["output_path"]).resolve()
        if path.parent!=editor.OUT.resolve() or not path.is_file() or path.suffix.lower()!=".mp4":
            raise ValueError("Revision file unavailable")
        db.execute("UPDATE assembly_exports SET output_path=?,caption_mode=? WHERE job_id=?",
                   (version["output_path"],version["caption_mode"],job))
    return history(w,c,job)


def create_thumbnail(w,c,job,timestamp):
    source,row=_row(w,c,job)
    if not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or not 0<=timestamp<row["total_seconds"]:
        raise ValueError("Choose a thumbnail timestamp within the video")
    target=editor.OUT/f"thumbnail_{job}_{uuid.uuid4().hex[:12]}.jpg"
    try:
        with tempfile.TemporaryDirectory(prefix=".thumbnail-",dir=editor.OUT) as scratch:
            staged=Path(scratch)/"frame.jpg"
            _ffmpeg(["-ss",str(timestamp),"-i",str(source),"-frames:v","1",
                     "-vf","scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                     "-q:v","2","-update","1",str(staged)],timeout=60)
            if not staged.is_file() or staged.stat().st_size<10:
                raise RuntimeError("Thumbnail was not generated")
            os.replace(staged,target)
        with core.connect() as db:
            db.execute("""INSERT INTO export_thumbnails(job_id,output_path,timestamp_seconds,source_output)
                VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET output_path=excluded.output_path,
                timestamp_seconds=excluded.timestamp_seconds,source_output=excluded.source_output,
                created_at=CURRENT_TIMESTAMP""",(job,str(target),timestamp,row["output_path"]))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"job_id":job,"timestamp_seconds":timestamp,"available":True}


def thumbnail_file(w,c,job):
    _row(w,c,job)
    with core.connect() as db:
        row=db.execute("SELECT output_path FROM export_thumbnails WHERE job_id=?",(job,)).fetchone()
    if not row:
        raise ValueError("Thumbnail not found")
    path=Path(row["output_path"]).resolve()
    if path.parent!=editor.OUT.resolve() or not path.is_file() or path.suffix.lower()!=".jpg":
        raise ValueError("Thumbnail file not found")
    return path


def recognize(source,language):
    model=core.DB.parent/"models"/"whisper-base"
    if not (model/"model.bin").is_file():
        raise RuntimeError("Install the optional faster-whisper model in data/models/whisper-base first")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install optional faster-whisper in the local Python environment") from exc
    engine=WhisperModel(str(model),device="cpu",compute_type="int8",local_files_only=True,cpu_threads=4)
    segments,_=engine.transcribe(str(source),language=language or None,vad_filter=True,beam_size=3)
    return list(segments)


def transcribe(w,c,job,language=None):
    source,row=_row(w,c,job)
    if language is not None and not re.fullmatch("[a-z]{2}",language):
        raise ValueError("Choose a two-letter language code or automatic detection")
    duration=row["total_seconds"]
    if duration>960:
        raise ValueError("Transcription is bounded to 16 minutes in this release")
    cues=[]; previous=0.0
    for segment in recognize(source,language):
        if not math.isfinite(segment.start) or not math.isfinite(segment.end):
            continue
        start=max(previous,0.0,round(segment.start,3))
        end=min(duration,round(segment.end,3))
        text=" ".join(segment.text.split()).replace("<","").replace(">","").replace("{","").replace("}","")[:400]
        if text and end>start:
            cues.append((start,end,text));previous=end
    srt=to_srt(cues)
    parse_srt(srt,duration)
    target=editor.OUT/f"transcript_{job}_{uuid.uuid4().hex[:12]}.srt"
    with target.open("x",encoding="utf-8") as f:
        f.write(srt)
    return target


def main():
    parser=argparse.ArgumentParser(description="Optional offline timed caption transcription")
    parser.add_argument("action",choices=["transcribe"])
    for name in ("workspace","channel","job"):
        parser.add_argument("--"+name,type=int,required=True)
    parser.add_argument("--language",default=None)
    args=parser.parse_args()
    print(transcribe(args.workspace,args.channel,args.job,args.language))


if __name__=="__main__":
    main()
