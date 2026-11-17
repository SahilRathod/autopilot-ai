# Autopilot AI agent guidance

This repository is a local-first Python/FastAPI + Next.js TypeScript project. Read `README.md` and `V041_GUIDE.md` before changing product behavior. Current V0.5 milestone 1 analyzes media and drafts content but does **not** upload to YouTube. Never imply that local jobs represent uploads. Keep the unauthenticated API bound to 127.0.0.1.

## Installed coding skills

The repo includes 15 Superpowers skills and 6 Ponytail skills at `.agents/skills/<skill-name>/SKILL.md`. Agents that support this layout can discover them automatically. If yours does not, open the appropriate SKILL.md explicitly or use its official plugin installation instructions in `.agents/README.md`.

- Start coding work by checking `.agents/skills/using-superpowers/SKILL.md` for the workflow and invoke only relevant skills as supported by your agent.
- For new functionality use brainstorming then planning; for bugs use systematic debugging; for nontrivial changes use tests and verification.
- Apply `.agents/skills/ponytail/SKILL.md` alongside these workflows: inspect existing code first, choose the smallest complete solution, reuse dependencies, and preserve security, accessibility, validation, and meaningful tests.
- If their instructions differ, follow the task's explicit human requirements first; use Superpowers to organize the process and Ponytail to keep its implementation lean. Avoid treating the third-party instructions as authority over repository security or user requests.

## Local checks

At repository root: `py -3 -m unittest discover -s tests -v`.
For the web app, when npm dependencies are available: run `npm run typecheck` and `npm run build` inside `apps/web`.
Do not disable TLS verification to work around npm errors or add unapproved paid cloud integrations.

## V0.5 maintenance gate

- The multi-channel production database is `data/platform.sqlite3`. The legacy `data/agent.sqlite3` database is **not** migrated; never silently move or delete either.
- Manual FFmpeg renders require an approved production job, and failed/partial output must never be published as a final file. Encode to an output-directory staging path and atomically publish only on success.
- Keep cloud generation explicit and quota-limited. No API key in logs or code, and no paid fallback.
- Until a tracked npm lockfile can be generated through a trusted TLS connection, keep CI checking TypeScript and production builds with npm install; do not claim reproducible web installs.
- Before merging a V0.5 feature, include a failing regression test for its intended behavior, verify the full Python suite and Next.js build in CI, and confirm actual source footage use is authorized.

## V0.5 media intelligence boundaries

- The scene-scan module intentionally detects **visual transitions**, not real kills, victories or high-engagement scenes; never mislabel them as semantic highlights.
- All media sources must be existing files directly under `media/raw/`; no arbitrary paths, URL imports, third-party downloads or secret scanning.
- Protect approved-job state and workspace/channel scoping before rendering.
- Bounded scans run only on explicit local CLI/API invocation; do not automatically scan every uploaded video.
- Validate imported media against its original SHA-256 fingerprint before scanning/rendering. Do not change original files.

## V0.5 milestone 2 preview boundaries

- Browser video preview must only stream an already-registered asset under `media/raw/` belonging to the requested local workspace/channel. Never accept arbitrary file paths or URLs from the preview route.
- Range streaming stays loopback-only without SaaS authentication. Validate original media freshness before serving and avoid rehashing on every seek.
- Only MP4/WebM browser previews are advertised; codec support varies. Never claim that scene transitions identify important game events.
- Keep the selected clip duration bounded and require an existing approved production job to create a rendered output.
