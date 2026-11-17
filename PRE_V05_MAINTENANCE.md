# Autopilot AI — Pre-V0.5 maintenance gate (17 November 2026)

**Base:** V0.4.1 `239b9b4e52da`. This is a local-first, one-creator platform, not an authenticated SaaS.

## Confirmed and corrected

1. **FFmpeg partial output leak:** A failed encoder could leave an incomplete final `.mp4`. Rendering now uses a unique temporary path in the output directory, replaces the destination only after successful processing, and always deletes its staging file. Regression tests cover both failure cleanup and successful publication.
2. **Invalid media timings:** `NaN`, `Infinity` and `-Infinity` could pass timestamp comparisons. All timestamps and source duration must now be finite.
3. **API release mismatch:** `/api/v1/health` and OpenAPI version were `0.4.0` even though the release was `0.4.1`; corrected with regression coverage.
4. **Agent documentation drift:** Updated the contributor guidance to point to the V0.4.1 guide and preserve render safety requirements.

## Verification gates

- `python -m unittest discover -s tests -v`: expected 25 tests, including maintenance regressions.
- `npm run typecheck` and `npm run build`: GitHub Actions web job.
- Review exact GitHub Actions run linked in the PR before treating this gate as complete.

## Deferred work: must not be misrepresented as complete

- No tracked `apps/web/package-lock.json`, so web dependency installs are not fully reproducible. Create a reviewed lockfile through a *trusted* npm registry connection, then change CI to `npm ci`.
- The user's local npm/TLS root trust failure is environmental; not bypassed.
- Legacy `data/agent.sqlite3` and modern `data/platform.sqlite3` remain separate; migration requires a backup, mapping rules and source-data tests.
- FFmpeg's full encode path is not validated with original footage on Windows. The subprocess tests use mocks.
- A process crash may leave a `job_renders` record in `rendering` state. Build explicit administrative recovery before unattended jobs.
- The HTTP API has no authentication. Keep `127.0.0.1` binding.
- Real Gemini and YouTube publishing operations are not exercised in CI; publishing remains disabled.
- `app/ai_director.py` still creates/validates database schema on each draft-generation call. Avoid optimizing it without benchmarks and migration tests.

## Recommended first V0.5 slice

Deliver a *reviewable media asset manifest* and offline clip analysis: validate footage locally with `ffprobe`, record duration/dimensions/codec to the correct workspace and channel, identify suggested candidate clips without inventing gameplay events, preview them, and allow manual approved FFmpeg rendering.

Do **not** add YouTube upload, voice cloning, always-on agents or new cloud dependencies as part of that slice. Optimize around a CPU-first workflow suited to local machines; verify on Windows before claiming hardware acceleration.
