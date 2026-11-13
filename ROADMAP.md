# Engineering roadmap (not implemented yet)

## Phase 1: Local MVP — included
- Configurable multi-game strategy and 4 content proposals
- SQLite job log, legal lifecycle transitions, human approval CLI
- Local video clip renderer for original footage (FFmpeg)
- Read-only localhost dashboard
- Dry-run scheduling state, basic tests, GitHub Actions CI

## Phase 2: Real creator workflow
- OAuth desktop login and encrypted token storage; YouTube Data API uploads
- API quota awareness, retries/backoff, idempotency, explicit publishing policies
- Gemini adapter with structured output and budget/usage ledger; offline fallback
- Transcription and forced subtitles (local model, resource permitting)
- Voice generation via own microphone or locally licensed TTS
- AI-assisted highlight selection via audio spikes, scene cuts, OCR and game-specific rules
- Portrait smart reframing and editable clip sequences

## Phase 3: Autonomous orchestration
- Durable queue + restart recovery, scheduler, operational alerts, dead-letter queue
- Analytics and engagement APIs with approval-gated public actions
- Controlled experiments with minimum sample sizes, no invented causal claims
- Multi-game content allocation based on measured engagement
- Local memory of approved scripts, video data, audience themes, rights evidence
- Periodic credential/token health checks and backup/restore

## Safety principles
- Publishing requires explicit approval by default
- Never fabricate gameplay, analytics, engagement, or licensing
- Use only footage you control or have permission to reuse
- No engagement bots/spam, fake giveaways, or impersonation
- Enforce no-paid-API configuration in code, not only natural-language instructions
