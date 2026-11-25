# Autopilot AI Roadmap

- **V0.2 complete:** Python CLI, workspaces/channels/jobs, manual gameplay trimming.
- **V0.3 this version:** FastAPI, Next.js TypeScript Creator Studio, local approvals and audit activity.
- **V0.4:** AI Director and model adapters (Gemini/local), script research, channel memory, usage caps.
- **V0.5:** Integrate FFmpeg workflows, highlight selection, captioning and niche-based production modules.
- **V0.6:** Secure YouTube OAuth, private uploads, approval-gated scheduling, analytics and comments.
- **V0.7:** Real scheduler and durable job worker, retries, backup, quotas, notifications.
- **V1.0:** Reliable multi-channel local creator studio.
- **V2.0 SaaS:** Authentication, organization memberships, PostgreSQL tenant security, hosted workers, metered billing.

Until V0.6, no real publishing occurs.

## V0.4 — AI Director (implemented)

- Offline content-pack templates; optional Gemini model, channel memory, caching, local cloud request caps.
- FastAPI endpoints and standalone Python CLI, reviewed job handoff, network-free unit tests.
- Future V0.5: video editor, captions, voice, visual asset pipeline and true multi-niche production.

## V0.4.1 — stabilization

- Atomic local cloud quota; deduplicated simultaneous calls, explicit Gemini model allowlist.
- Format-aware, channel-memory-aware offline content, structured Gemini response schema.
- AI Director UI, canonical job content read endpoint, CORS PUT and safer state transitions.
- Manual approved FFmpeg rendering into platform job output registry.
- Legacy SQLite migration and tracked npm lockfile are deferred until tested on source data / a trusted registry connection.

## V0.5 milestone 1 — media intelligence

- Implemented: local FFprobe metadata, SHA-256 source checking, per-channel media assets, bounded FFmpeg visual scene transitions, suggested clip windows, approved-job render handoff, Python CLI and FastAPI routes.
- Next milestones: candidate preview in dashboard, real gameplay-event heuristics, captions, audio handling, validated media manifests and media-production scheduling.
- No live uploads or automatic publishing.

## V0.5 milestone 2 — video preview studio

- Integrated Media Studio tab with channel library, native browser playback, visual scene markers, bounded candidate playback, and explicit approved-job rendering.
- Added scoped no-store HTTP range streaming for registered MP4/WebM originals; file integrity cached by size and high-resolution timestamps.
- Next: richer timeline editing, frame thumbnails, caption support, audio/music processing with rights checks, and true gameplay-event analysis.

## V0.5 milestone 3 — offline clip ranking

- Built: low-rate local audio energy sampling, relative transient strengths, preset-weighted visual/audio heuristics, explainable ranking and persistence, dashboard ordering and API/CLI access.
- Known limits: no OCR game HUD, kill feed detection, multi-game event models or audio-source separation. Music and narration may trigger high energy; always review.
- Next: semantic gameplay event analysis with opt-in local lightweight models and training data, subject to device performance and verified consent/rights; V0.5 milestone 4 can focus on captions and export assembly.

## V0.5 milestone 4 — captions and export assembly

- Implemented: ordered multi-candidate MP4 assembly; creator-authored text-to-SRT caption cards, soft or burned subtitle export; source/padded audio, loudness normalization or mute; fast and high-quality 9:16/16:9 presets; previewable local exports.
- Per-job SQLite records and mutually exclusive legacy/assembled render claims; original source SHA-256 and channel boundaries remain enforced.
- Limitations: captions are **not** speech transcription, generated timing is approximate; no voice synthesis, music license sourcing, YouTube upload, or persistent background renderer.
- Next: local STT as an explicit opt-in optional dependency, verified subtitle timing, durable render queue and preview thumbnails before any SaaS/public deployment.

## V0.5.1 working-product priority

- Keep master usable; test on isolated feature branches/worktrees with separate data.
- Durable assembly queue, FFprobe validation, Windows launcher, database backup and actual FFmpeg CI are the first stabilization slice.
- Next: real YouTube OAuth/read-only channel link, private upload with explicit approval, versioned migrations, render recovery and browser tests. Do not claim live integration without verification.

## V0.6 account connection

- Windows DPAPI-protected Google refresh token, PKCE and local callback; read-only channel information and statistics.
- Next gate: real authorization on the user's machine, then private resumable uploads with separate upload permission.
