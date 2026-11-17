# Autopilot AI V0.5 — Milestone 2 Video Preview Studio

The second V0.5 milestone adds visual inspection of your existing game recordings in the Next.js Creator Studio. It uses the Media Intelligence backend from Milestone 1 and does **not** add cloud AI, YouTube uploads, or background rendering.

## Start on Windows

From the repo root:

```powershell
cd D:\AutoCopilot\autopilot-ai
git pull origin master
ffmpeg -version
ffprobe -version
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell window:

```powershell
cd D:\AutoCopilot\autopilot-ai\apps\web
npm install
npm run dev
```

Open http://127.0.0.1:3000 and choose **Media Studio** from the navigation.

If npm still returns E403 / `SEC_E_UNTRUSTED_ROOT`, fix the trusted certificate/registry access first; do not disable TLS verification. Python CLI operations remain available without npm.

## Workflow in Media Studio

1. Choose a channel. Put footage that you own or are licensed to use in the repository's `media/raw/` folder.
2. Enter the exact local filename, such as `gameplay.mp4`, and choose **Register footage**. This adds metadata to SQLite without uploading or copying the video.
3. Select the imported file. The browser uses its native media controls for scrubbing and playback.
4. Set clip length and visual scene sensitivity, then choose **Find candidate clips**. Up to eight approximate visual transition windows are saved to the selected channel.
5. Click any clip card or its timeline marker to seek to the proposed start. **Play selected clip** plays that time interval and stops at its end.
6. For rendering, open **Production queue**, create a job for the same channel, submit it to review and explicitly approve it in **Approval center**.
7. Return to **Media Studio**, select the candidate and approved job, then choose **Render reviewed clip**. The output is saved locally in `media/output/`, never uploaded to YouTube.

Important: `scene_change` means a visual transition detected by FFmpeg at low resolution. It is **not** a detected kill, victory, engagement score, or proof of valuable content.

## Preview backend and safety

`GET /api/v1/workspaces/{w}/channels/{c}/media/assets/{asset_id}/preview` provides byte-range playback for already imported MP4/WebM files. It validates the workspace/channel, ensures the filename is still inside `media/raw/`, and checks the registered SHA-256 fingerprint. After a successful checksum, repeated range requests reuse it only while file size, modification time and change time remain unchanged. Responses are `private, no-store`.

Browser playback requires a compatible video codec (typically H.264 MP4 or suitable WebM). MOV/MKV or incompatible codecs can still be analyzed with FFmpeg through the CLI, but the browser preview endpoint does not transcode them automatically. No external CDN is involved.

The FastAPI service is **local-only and unauthenticated**, so always run it on 127.0.0.1. Do not expose either server publicly. The Next.js app also uses a loopback rewrite, not a secure SaaS authentication gateway.

## Verification

```powershell
cd D:\AutoCopilot\autopilot-ai
py -3 -m unittest discover -s tests -v
cd apps\web
npm run typecheck
npm run build
```

Python tests verify range streaming, workspace isolation, stale-video conflicts and checksum reuse. GitHub CI checks TypeScript and a production build. Tests are not a substitute for manual playback/encoding verification on your Windows laptop.

## Future V0.5 work

Timeline trimming adjustments, generated preview thumbnails, true gameplay-event signals, subtitles/voiceover and export presets remain for later milestones. This release intentionally uses only existing Python, FastAPI, Next.js and FFmpeg dependencies.
