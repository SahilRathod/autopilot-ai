# Autopilot AI — V0.5.1 Working Creator Studio

Local-first multi-channel AI drafting, media analysis, and **approved local MP4 draft assembly**. Still not an automatic speech transcription service or YouTube uploader.

## V0.5.1 — Local render reliability
- Durable assembly render tasks with a separate local worker and dashboard state polling.
- Output stream/duration validation with FFprobe for queued assemblies.
- Windows launcher, database snapshots, dependency diagnostics and configurable dev API port.
- [Working-product setup and recovery guide](WORKING_RELEASE.md).

## V0.5 milestone 4 — Captions and local draft assembly
- Select up to eight scene candidates in a deliberate playback order and assemble them into one MP4 for an approved production job.
- Export fast or high-quality Short (portrait) / long-form (landscape) formats, with source audio preserved, single-pass normalization, or mute.
- Use creator-written caption lines as evenly timed **caption cards**. Embed switchable MP4 subtitles or burn captions into the picture with an FFmpeg libass build. This **does not** transcribe speech or align captions to voice automatically.
- Preview finished local MP4 exports via the Media Studio UI or use the Python-only CLI, no npm needed.
- Approval, workspace/channel checks, atomic output publication and non-overlapping legacy/assembly job claims.
- [V0.5 Milestone 4 usage and limitations](V05_M4_GUIDE.md). No automatic uploads or paid APIs.

## V0.5 milestone 3 — Offline ranking and explainable audio heuristics
- Decode at most 600 seconds of existing audio using FFmpeg (mono 8kHz PCM), calculate 0.5-second RMS windows, and identify **relative energy spikes**. No internet or new Python dependencies.
- Rank existing, scanned clip candidates by a user-selected **balanced**, **tactical action** (e.g. Valorant/CS) or **sandbox exploration** (e.g. Minecraft) preset.
- Persist profile-specific scores and evidence per channel. Rescanning removes stale scores. Silent/no-audio footage falls back to visual cues.
- Media Studio sorts scored clips and explains each recommendation; scores **are not probabilities** or game-event detections.
- Available through FastAPI, the Next.js UI and the no-npm Python CLI. See [V0.5 milestone 3 guide](V05_M3_GUIDE.md).

## V0.5 milestone 2 — Video Preview Studio
- New **Media Studio** dashboard tab: channel-scoped media library, HTML video preview, visual scene markers and candidate clips.
- Preview original MP4/WebM files locally with browser byte-range seeking. Repeated range requests reuse a cached source hash until file size/timestamps change.
- Register footage already in `media/raw/` by filename; perform bounded scene scans and play a selected clip interval.
- Render a selected candidate only against a reviewed, approved job belonging to the same channel. **No publishing, uploads or external API costs.**
- Full setup and limitations: [V0.5 Milestone 2 Guide](V05_M2_GUIDE.md).

## V0.5 media intelligence (milestone 1)
- Import original footage by local filename under `media/raw/`, with FFprobe metadata and SHA-256 source verification.
- Discover possible clip cut points from bounded, downsampled FFmpeg scene-change analysis. These are **visual transition candidates, not scored highlights**.
- Store per-channel media assets and clip candidates in the existing platform SQLite database.
- Inspect candidates through `app.platform_cli` or local FastAPI `/docs`. Render selected clips **only for approved jobs**.
- See [V0.5 usage guide](V05_GUIDE.md). No npm is required for the Python CLI.

## V0.4.1 improvements
- Fixed cost cap=0, concurrent atomic reservations, and duplicate in-flight Gemini requests.
- Short/long templates now differ; channel memory affects offline generation.
- AI Director is available in the Next.js dashboard; review AI script content from linked jobs.
- Approved platform jobs can render media through manual FFmpeg CLI and store output paths.
- [V0.4.1 setup and limitations](V041_GUIDE.md)

## V0.4 AI Director

- Draft title, hook, outline, script template, description, keywords, Shorts concepts and verification checklist.
- Persistent per-channel memory, SQLite drafts, 24-hour cache, offline mode and optional Gemini 2.5 Flash-Lite.
- No npm needed for Python-only AI CLI. See [V0.4 setup](V04_GUIDE.md).
- Cloud calls are off by default; draft handoff never publishes to YouTube.

## Features
- Next.js + TypeScript dashboard for workspaces, channel profiles, jobs, review approvals and audit history.
- FastAPI endpoints with validation, SQLite persistence, workspace scoping and OpenAPI docs.
- Original Python CLI and FFmpeg gameplay clip editor preserved.
- Offline zero-cost defaults, optional explicitly enabled Gemini API calls. No YouTube uploads or background jobs.

## Windows quick start
Requirements: Python 3.11+, Node.js >=20.9, Git. FFmpeg/FFprobe required for media import, scene analysis, and rendering.

**Terminal 1 (repository root)**
```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 (repository root)**
```powershell
cd apps/web
npm install
npm run dev
```

**Terminal 3 (repository root)**
```powershell
.\.venv\Scripts\python.exe -m app.render_queue
```

Or use `./start.ps1` for all three services after setup. Open http://127.0.0.1:3000. API docs: http://127.0.0.1:8000/docs.

## Test
```powershell
# In repository root
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# In apps/web after installing npm dependencies
npm run typecheck
npm run build
```

## Limitations
The servers must remain on 127.0.0.1 because authentication and real tenant isolation are not implemented. Do not deploy this base publicly. The queued/completed statuses are LOCAL workflow labels, not YouTube uploads. The old gaming CLI has a separate database; V0.4.1 adds a manual platform job rendering bridge without migrating old records.
Read BASE_ARCHITECTURE.md and ROADMAP.md for future plans.

## YouTube account connection (V0.6 first slice)

Windows-only, opt-in read-only Google desktop OAuth. See [YouTube setup](YOUTUBE_SETUP.md). Private uploads are not enabled in this slice.
