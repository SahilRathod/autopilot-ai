# V1.0 release acceptance

This is a **release candidate**, not a production-certified V1.0. Automated CI uses synthetic media and mocked Google responses. Never mark a remote integration or a hardware performance target complete without evidence.

## Implemented local product

- Multi-workspace, channel-scoped jobs, offline content packs, optional quota-controlled Gemini, draft editing and approval.
- Existing local footage import, bounded scene analysis and explainable audio/visual ranking (not semantic gameplay events).
- Approved durable render worker, validated MP4, timed captions, narration mixing, frame thumbnail, immutable export revisions and optional offline speech recognition.
- Local scheduled draft preparation and optional footage suggestions.
- Windows DPAPI / PKCE YouTube account connection, explicit private resumable upload, actual on-demand video metrics, optional Analytics API reports, separate approved future publication and individual comment replies.
- Local backup, startup, audit activity, ambiguous remote action review and isolated development.

## Automated gates

- Python regression suite on Ubuntu and Windows, real FFmpeg available on both.
- Windows DPAPI credential round-trip; migration of an existing upload-enabled channel and validated pre-upgrade backup.
- TypeScript check, production Next build and real Chromium against a separate temporary FastAPI/SQLite instance.
- No live Google requests or production database use in automated tests.

## Windows acceptance (required before final V1.0)

1. Stop the old services. Copy the data folder and preserve media/raw and media/output before upgrading. Keep the previous working checkout.
2. Update using git pull --ff-only origin master. Run the maintenance doctor and Python regression suite; start with start.ps1. Verify the health endpoint and dashboard.
3. Run the isolated local acceptance command below. Then create a disposable workspace/channel. Import your own short gameplay clip, scan and rank it, review an offline draft, approve a job, assemble and preview a real MP4. Verify duration and audio, subtitles, narration mix, thumbnail, and revisions. Stop/restart the worker with a queued job and confirm the expected local state.
4. If using optional Whisper or Gemini, test them with a small sample and your own explicit setup and budget; inspect content before approval. Neither is mandatory for the offline workflow.
5. Enable YouTube Data API v3 and optionally YouTube Analytics API in your own Google Cloud project. Save the desktop OAuth client JSON in the ignored data directory. Follow YOUTUBE_SETUP.md. Consent on your Windows user account; verify the actual linked channel, then separately grant upload/analytics permissions.
6. Upload an approved harmless test export privately. Verify the actual video ID, private visibility, and successful playback in YouTube Studio. Verify real analytics counts with the provider. On a test channel only, if desired, separately authorize management, review the exact video, explicitly schedule a future public time and verify or cancel the schedule in YouTube Studio. Test an individual approved reply only when appropriate. Do not grant permissions or schedule a publication solely to satisfy a test.
7. Record test results, errors, Windows version, available disk space, FFmpeg version, and actual render duration. Remove/revoke disposable links and keep production credentials private.

## Known limits and release boundaries

- Local loopback only; no SaaS tenant authentication, public server, billing or unattended publishing. Public schedules and replies require explicit creator approval.
- Actual Google eligibility, OAuth consent, private upload, analytics and remote mutations remain provider/account-dependent. Verify them before declaring a final production release. Do not bypass Google API verification or upload restrictions.
- Local footage is required. No automatic game-event recognition, full editing timeline, trend scraper, or AI-generated thumbnail art. Optional STT inference and hardware acceleration benchmarks require actual laptop testing.
- Ambiguous interrupted FFmpeg claims and remote requests require operator review, not blind retries. The legacy agent database is not silently migrated. Web dependency lockfile remains a reproducibility improvement.
- Keep the working checkout available during development; use a separate worktree with separate data/media and dev ports.

**Final V1.0 decision:** only after the relevant Windows and real account acceptance results are recorded, not just because version metadata says 1.0.

## Automated acceptance on your laptop (RC2)

Run from the repository root in PowerShell after installing requirements and FFmpeg:

```powershell
.\.venv\Scripts\python.exe -m app.acceptance | Tee-Object -FilePath acceptance-report.json
```

For an actual footage sample you own, use the optional argument (example filename; substitute your own):

```powershell
.\.venv\Scripts\python.exe -m app.acceptance --footage "media/raw/your-clip.mp4" | Tee-Object -FilePath acceptance-report.json
```

The runner copies at most 250 MiB of existing video into a temporary sandbox (minimum two seconds), or generates a synthetic sample locally. It exercises the real planner/ranking/approval/render pipeline, a simulated interrupted queue claim, caption mux, narration tone mixing, thumbnail extraction, revision preservation and database backup. It restores application paths and deletes temporary data; it never uploads, calls Google/Gemini, or uses your production database. The JSON records OS, CPU count, free temporary disk, FFmpeg version and measured output resolution/render seconds. A failed stage returns a nonzero exit code. Share the report if you want help diagnosing a failure. No user video contents, credentials or source paths are included. The report is evidence for local execution only: inspect actual video quality separately, and test OAuth and real YouTube operations separately. Optional AI verification is not included.
