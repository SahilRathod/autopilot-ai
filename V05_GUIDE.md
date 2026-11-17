# Autopilot AI V0.5 — Media Intelligence (Milestone 1)

**Scope:** local original footage import, metadata analysis, scene-transition candidates, manual reviewed clip renders. No paid API, no external uploads, no autonomous video publisher. Scene changes are not reliable gaming highlights.

## Setup on Windows 11

From `D:\AutoCopilot\autopilot-ai`:

```powershell
git pull origin master
ffmpeg -version
ffprobe -version
py -3 -m app.platform_cli init
py -3 -m unittest discover -s tests -v
```

Put footage you own or can legally use into `media/raw/` (for example `gameplay.mp4`). If FFmpeg or FFprobe is missing, install FFmpeg using its official Windows builds and add the binaries to PATH. Avoid insecure npm TLS workarounds; **no npm is needed for this Python feature**.

Your workspace and channel IDs must already exist, or create them using `workspace-add` and `channel-add` as described in the V0.4.1 guide.

## Import and inspect metadata

```powershell
py -3 -m app.platform_cli media-import --workspace 1 --channel 1 --source "gameplay.mp4"
py -3 -m app.platform_cli media-list --workspace 1 --channel 1
```

Importing does not duplicate the footage. It saves the filename, SHA-256, duration, resolution, frame rate, and video/audio codecs in `data/platform.sqlite3`. Re-importing unchanged footage into the same channel returns its existing asset ID.

## Discover potential clip boundaries

Use the imported `asset_id`:

```powershell
py -3 -m app.platform_cli media-scan --workspace 1 --channel 1 --asset 1 --seconds 25 --threshold 0.35 --scan-seconds 120
py -3 -m app.platform_cli media-candidates --workspace 1 --channel 1 --asset 1
```

Scene scan samples footage at 2 frames per second at 160-pixel width, with a maximum scan window of 600 seconds. It returns up to 8 candidate windows. At least one opening clip is always offered, even if no scene transitions are detected. Adjust `--threshold` between 0.05 and 0.95. Candidates are approximate **visual edit points**; review the raw gameplay and use your own judgment.

## Render the chosen candidate

First create a production job **in the same workspace/channel** and explicitly transition it from `draft` to `ready_for_review` and then `approved`, or use the existing dashboard approval center.

```powershell
py -3 -m app.platform_cli job-add --workspace 1 --channel 1 --title "Best gameplay moment" --format short
py -3 -m app.platform_cli transition --workspace 1 --job 1 --to ready_for_review
py -3 -m app.platform_cli transition --workspace 1 --job 1 --to approved
py -3 -m app.platform_cli media-render --workspace 1 --channel 1 --candidate 2 --job 1
```

Replace all IDs with the actual IDs returned. Render output is saved under `media/output/` and tracked in the new database, using the hardened atomic FFmpeg publication path. This does not upload to YouTube.

## HTTP API

Start FastAPI on loopback only; browse `http://127.0.0.1:8000/docs` under **V0.5 Media Intelligence**. Routes under `/api/v1/workspaces/{w}/channels/{c}/media`:

- `POST /import` — body `{"filename":"gameplay.mp4"}`
- `GET /assets`, `GET /assets/{asset_id}`
- `POST /assets/{asset_id}/scan` — body `{"clip_seconds":25,"threshold":0.35,"max_scan_seconds":120}`
- `GET /assets/{asset_id}/candidates`
- `POST /candidates/{candidate_id}/render` — body `{"job_id":1}`; job must already be approved

## Engineering caveats

- Single creator, loopback-only, no API authentication or public SaaS tenancy.
- Files are hashed during import and verified again before scan/render. Large files take longer to hash.
- FFmpeg scan is intentionally CPU-only and bounded. It does not detect real game events, automatically pick the best clip, or create subtitles.
- Source records reference original filenames; moving/removing or changing a source requires re-import.
- Re-running a scan replaces previous candidates. Older candidate IDs cannot be reused after rescan.
- No real Windows GPU benchmark or third-party footage rights verification has been performed.
- npm/TLS certificate and lockfile issues remain separate.
