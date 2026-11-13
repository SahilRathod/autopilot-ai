"""Local FFmpeg pipeline. Requires ffmpeg and ffprobe executables on PATH."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RAW=(ROOT/'media'/'raw').resolve()
OUT=(ROOT/'media'/'output').resolve()


def source(name):
    # Only allow filenames inside the ingest directory, never arbitrary paths.
    p=(RAW/name).resolve()
    if p.parent != RAW or not p.is_file() or p.suffix.lower() not in {'.mp4','.mov','.mkv','.webm'}:
        raise ValueError('Use an existing video filename in media/raw/')
    return p


def probe(p):
    if not shutil.which('ffprobe'): raise RuntimeError('Install FFmpeg and add it to PATH')
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','json',str(p)],capture_output=True,text=True,check=True)
    return float(json.loads(result.stdout)['format']['duration'])


def highlight(name, start=0, seconds=30, vertical=True, filename='highlight.mp4'):
    p=source(name)
    if not shutil.which('ffmpeg'): raise RuntimeError('Install FFmpeg and add it to PATH')
    duration=probe(p)
    if start < 0 or seconds <= 0 or start+seconds > duration+0.1:
        raise ValueError(f'Clip exceeds source duration ({duration:.1f}s)')
    OUT.mkdir(exist_ok=True)
    target=(OUT/filename).resolve()
    if target.parent != OUT or target.suffix.lower()!='.mp4': raise ValueError('Invalid output name')
    vf=("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
        if vertical else "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1")
    subprocess.run(['ffmpeg','-y','-ss',str(start),'-i',str(p),'-t',str(seconds),
      '-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','25',
      '-c:a','aac','-b:a','128k','-movflags','+faststart',str(target)],check=True)
    return str(target)
