# Autopilot AI V0.5 — Milestone 3: Smarter Offline Clip Ranking

Milestone 3 builds on the Media Studio preview from Milestone 2. It ranks the *existing visual scene candidates* using **relative audio-energy spikes** and game-style weighting presets. This is a transparent, locally executed heuristic, **not** actual gameplay event detection or predictive engagement scoring.

## Why this design?

The project currently runs on a Windows 11 laptop with limited dedicated GPU memory and zero extra API budget. We use FFmpeg to decode mono 8kHz, 16-bit PCM, calculating 0.5-second root-mean-square (RMS) energy bins in Python's standard library. The audio segment is capped to 600 seconds, uses no local deep-learning model or paid API, and leaves your source files unchanged.

The preset is a *user preference*, not a recognized video game:
- `balanced`: equal influence of relative audio spikes and visual transition candidates
- `tactical`: more weight on audio spikes (a reasonable starting point for Valorant / CS style footage)
- `sandbox`: more weight on visual transitions (a starting point for Minecraft / sandbox clips)

A scene boundary is only evidence of a visual change; an audio transient is only a change in volume. Music, narration, hard cuts, compression and game UI can cause false positives. **Scores are not percentages of confidence.**

## Windows installation and testing

From the repository root:

```powershell
cd D:\AutoCopilot\autopilot-ai
git pull origin master
ffmpeg -version
ffprobe -version
py -3 -m unittest discover -s tests -v
```

Put original gameplay you own or have permission to use in `media/raw/gameplay.mp4`. You must already have workspace and channel IDs. If not, create them using the V0.5 Milestone 1 guide.

## Fast no-npm CLI

```powershell
py -3 -m app.platform_cli media-import --workspace 1 --channel 1 --source "gameplay.mp4"
py -3 -m app.platform_cli media-scan --workspace 1 --channel 1 --asset 1 --seconds 25 --scan-seconds 120
py -3 -m app.platform_cli media-rank --workspace 1 --channel 1 --asset 1 --profile tactical --scan-seconds 120
py -3 -m app.platform_cli media-rankings --workspace 1 --channel 1 --asset 1 --profile tactical
```

Replace example IDs with actual returned IDs. If media assets/candidates already exist, you can skip re-import and re-scan. The output contains candidate IDs, heuristic score from 0–100, audio analyzed flag, audio and visual sub-scores, and specific reasons for the ordering.

For silent media or recordings with no audio track, the scorer uses visual transitions only.

## Dashboard

Start FastAPI locally on `127.0.0.1:8000` and the existing Next.js dashboard on `127.0.0.1:3000`. In **Media Studio**:

1. Select a channel, asset, and run **Find candidate clips** if necessary.
2. Select **Clip-ranking preset**: Balanced, Tactical action, or Sandbox exploration.
3. Click **Rank clips locally**. Ranked cards move to the top and display heuristic scores.
4. Select a card to preview the interval and read the **Why this clip was recommended** explanation.
5. Render only after assigning the selected clip to an **approved production job**. Publishing remains disabled.

If your Windows npm certificate issue persists, the CLI provides the same scoring without the dashboard.

## FastAPI

Under `/api/v1/workspaces/{w}/channels/{c}/media`:
- `POST /assets/{asset_id}/rank` with body `{"profile":"tactical","max_seconds":120}`
- `GET /assets/{asset_id}/rankings?profile=tactical`

Media import, scanning, preview and rendering endpoints from previous milestones remain intact. No data crosses channel boundaries. A new scan removes obsolete candidate scores.

## Verification and limitations

GitHub Actions runs Python regression tests and Next.js typechecks/builds. Unit tests mock FFmpeg for deterministic scoring; real audio/video on your Windows machine must still be tried separately. Live game event detection, captions, ML-assisted highlights, video editing timelines, and uploading are not part of this milestone. The HTTP API has no login; keep it on loopback.
