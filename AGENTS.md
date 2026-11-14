# Autopilot AI agent guidance

This repository is a local-first Python/FastAPI + Next.js TypeScript project. Read `README.md` and `V04_GUIDE.md` before changing product behavior. Current V0.4 drafts content but does **not** upload to YouTube. Never imply that local jobs represent uploads. Keep the unauthenticated API bound to 127.0.0.1.

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
