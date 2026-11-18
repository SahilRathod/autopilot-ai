# Autopilot AI V0.5 — Milestone 4: Captions and Local Draft Assembly

Milestone 4 turns manually selected scene candidates into **one local draft MP4**, only after its production job has been approved. It reuses the existing FastAPI, FFmpeg, SQLite and Next.js Media Studio.

**What it does NOT do:** No speech-to-text, voice cloning, copyrighted music search, scheduled worker, gameplay event recognition, or YouTube uploading. Caption lines are written by the creator and spaced evenly over the assembled duration; they are **not synchronized to spoken words**.

## Requirements and update

From the repository root on Windows:

```powershell
cd D:\AutoCopilot\autopilot-ai
git pull origin master
ffmpeg -version
ffprobe -version
py -3 -m unittest discover -s tests -v
```

Install an official FFmpeg build and make sure both executables are on PATH. The **burned captions** option requires an FFmpeg build with the `subtitles` filter (libass); `ffmpeg -filters` should list `subtitles`. Soft MP4 subtitles use the `mov_text` encoder.

### Option A — Media Studio dashboard

1. Place a recording you own or are allowed to edit in `media/raw/`. Register it in the **Media Studio** tab.
2. Run scene analysis (optional: rank candidates). Review the original footage, select up to 8 candidate clip checkboxes, and use the up/down controls to choose playback order.
3. Create a job in **Production queue** for the same channel. Submit it for review and approve it in **Approval center**.
4. In **Draft video assembly**, choose the approved job. Pick **Fast** or **High quality**, and **Preserve**, **Normalize**, or **Mute** audio.
5. Choose caption delivery: **None**, **Soft (switchable)**, or **Burn (always visible)**. If captions are enabled, write one caption line per text card (maximum 40, 160 characters each). They are spaced evenly across the exported duration.
6. Click **Assemble local MP4**. Browse **Finished local exports** to preview it after rendering. No YouTube upload is performed.

Open the local dashboard after starting your backend and web app in separate PowerShell windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
# In another terminal:
cd apps\web
npm run dev
```

If the existing Windows npm certificate issue blocks the dashboard, use the Python CLI below. Do **not** disable TLS certificate verification.

### Option B — Python CLI without npm

Assume workspace 1 and channel 1 exist and you already imported/scanned footage. Determine the real IDs from:

```powershell
py -3 -m app.platform_cli media-list --workspace 1 --channel 1
py -3 -m app.platform_cli media-candidates --workspace 1 --channel 1 --asset 1
py -3 -m app.platform_cli jobs --workspace 1 --channel 1
```

Create and explicitly approve a new job, if you do not already have one:

```powershell
py -3 -m app.platform_cli job-add --workspace 1 --channel 1 --title "Reviewed Montage" --format short
py -3 -m app.platform_cli transition --workspace 1 --job 1 --to ready_for_review
py -3 -m app.platform_cli transition --workspace 1 --job 1 --to approved
```

Replace all example IDs. For no captions:

```powershell
py -3 -m app.platform_cli media-assemble --workspace 1 --channel 1 --job 1 --candidates 1 2 --quality fast --audio preserve --captions none
```

For manually timed caption cards, create a UTF-8 file with one caption per line (for example `captions.txt`, containing two lines of your own text), then:

```powershell
py -3 -m app.platform_cli media-assemble --workspace 1 --channel 1 --job 2 --candidates 3 4 --quality fast --audio normalize --captions soft --caption-file captions.txt
py -3 -m app.platform_cli media-exports --workspace 1 --channel 1
```

Use a **new approved job for every export**. An approved job cannot already have a legacy single-clip render or another assembly. Long-form clips must fit within 30 minutes total; Shorts within 3 minutes. Candidate IDs must belong to the selected channel.

### Presets and audio

| Selection | Fast | High |
| --- | --- | --- |
| Short portrait | 720×1280 (H.264) | 1080×1920 (H.264) |
| Long landscape | 1280×720 (H.264) | 1920×1080 (H.264) |
| Audio preserve | Source audio to AAC; missing audio becomes silence | Same |
| Audio normalize | Single-pass FFmpeg loudnorm to AAC | Same |
| Audio mute | AAC silence | Same |

All segments are transcoded to a consistent frame rate and resolution, concatenated, then optionally subtitle-muxed or burned. Export files are saved in `media/output/`, with temporary files cleaned on normal failures; the originals are never modified.

### FastAPI

On `http://127.0.0.1:8000/docs` under **V0.5 Media Intelligence**, these routes are available:

- `POST /api/v1/workspaces/{w}/channels/{c}/media/assemble`
- `GET /api/v1/workspaces/{w}/channels/{c}/media/exports`
- `GET /api/v1/workspaces/{w}/channels/{c}/media/exports/{job_id}/preview`

Example assembly JSON:

```json
{
  "job_id": 3,
  "candidate_ids": [7, 8],
  "quality": "fast",
  "audio_mode": "normalize",
  "caption_mode": "soft",
  "caption_lines": ["Welcome to the video", "Thanks for watching"]
}
```

The API is unauthenticated and for **loopback-only local development**. Do not expose it on a network.

### Known limitations and operational safety

- **No automatic caption transcription:** typed text is timed evenly, so creators must check words and timing against the actual audio.
- Audio normalization is single-pass and per clip; dramatic loudness differences may remain. The FFmpeg build must contain the required audio/video encoders and subtitle filters.
- Rendering is synchronous. Multi-minute 1080p exports can outlast browser or Next.js proxy timeouts; use the local CLI for large jobs. A future durable worker will address this.
- Process crashes can leave a `rendering` database claim; a documented recovery process and durable queue are future work. Never manually delete claims while an encoder is active.
- No file upload via HTTP: input footage must already be placed in `media/raw/`. Finished videos are accessible locally by an ID-scoped preview endpoint and are not sent to YouTube.
- Real video encoding is verified separately with synthetic FFmpeg clips; GitHub CI may skip FFmpeg-dependent tests when the binaries are absent. Actual Windows footage still requires validation.
