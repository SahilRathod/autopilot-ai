# Coding-agent skill integration

This folder vendors the **skill content** (not the full plugins, lifecycle hooks, automatic session injection or external binaries) for:

- [Superpowers](https://github.com/obra/superpowers) by obra, 15 skills and supporting textual resources, pinned to commit `22f0b463e7a5e579904dd6211a520321035526f7`.
- [Ponytail](https://github.com/DietrichGebert/ponytail) by DietrichGebert, 6 skill definitions, pinned to commit `96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`.

Both projects use the MIT license; see `.agents/licenses/`. These are third-party instructions for the **coding assistant** developing Autopilot AI, not runtime AI models or code required for the video pipeline.

## Getting started

Open this repository with an agent that recognizes `.agents/skills`. If it doesn't auto-discover skills, point your agent to `AGENTS.md` and the applicable `SKILL.md`. For automatic hooks, lifecycle activation, and plugin commands use the original full plugin install instructions:

- [Superpowers README](https://github.com/obra/superpowers#installation)
- [Ponytail INSTALL](https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md)

Example: in a coding-agent chat, ask: "Read AGENTS.md and use Superpowers planning plus Ponytail's smallest-complete-change guidance before implementing this change."

## How they work together

Superpowers: clarify/plan, isolate work, implement with tests, debug, review, verify. Ponytail: use existing code and platform features instead of unnecessary dependencies and abstractions. Neither skill grants new tool permissions, removes context limits, or makes the current app autonomously publish YouTube videos.

To refresh versions, review upstream changes and licensing, then replace these vendored files at a known commit. Never run unreviewed upstream scripts automatically.
