# Autopilot AI — Local Multi-Channel Base (v0.2)

A free, Python-standard-library starter for an eventual multi-channel YouTube automation SaaS. Based on our original Gaming Autopilot AI MVP; original gameplay clip tools are retained.

## Windows quick start

Requires Python 3.11+; no pip packages required for database and queue management.

```powershell
cd $HOME\Documents\autopilot-ai-base
py -3 -m app.platform_cli init
py -3 -m app.platform_cli workspace-add "My Studio"
py -3 -m app.platform_cli channel-add --workspace 1 --name "Gaming Hub" --niche gaming
py -3 -m app.platform_cli channel-add --workspace 1 --name "AI Tutorials" --niche technology
py -3 -m app.platform_cli channels --workspace 1
py -3 -m app.platform_cli job-add --workspace 1 --channel 1 --title "Valorant Tips" --format short
py -3 -m app.platform_cli jobs --workspace 1
py -3 -m unittest discover -s tests -v
```

For existing gameplay editor and dashboard:

```powershell
py -3 -m app.cli init
py -3 -m app.cli plan
py -3 -m app.cli serve
```

Dashboard: http://127.0.0.1:8765 (legacy gaming queue; multi-channel dashboard is not yet implemented).

## What's real

- Local workspaces, multiple channel profiles, distinct video jobs, audit trail, status transitions with review gate.
- Defaults: INR 0 budget, publishing disabled.
- Preserved original FFmpeg gameplay trimming commands and local dashboard, **not yet integrated** into multi-channel queue.

## What's not real yet

- Multi-user login / secure SaaS tenant isolation
- AI API integration, game highlight recognition, live research or captions
- YouTube uploads, subscription billing, cloud workers or unattended scheduling

See `BASE_ARCHITECTURE.md` and `ROADMAP.md`.
