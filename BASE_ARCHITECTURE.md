# Autopilot AI — foundation architecture

## Now: local-first multi-channel product

- `workspaces` own `channels` and `production_jobs`.
- Every job is scoped to a workspace and a channel.
- `audit_log` records critical operations.
- All publishing disabled by default; `queued` only marks local status.
- Channel-level budget defaults to INR 0.
- Existing gameplay MVP remains runnable under `python -m app.cli`.
- New multi-channel management commands are under `python -m app.platform_cli`.

## Future: SaaS architecture boundaries

1. Authentication (OAuth/passkeys), organization memberships and RBAC; **never** trust client-provided tenant IDs.
2. Replace SQLite with PostgreSQL and database-enforced tenant isolation / RLS, migration tooling.
3. Queue workers, durable retries, idempotency keys and explicit approval tokens.
4. Encrypted YouTube OAuth credentials per channel; refresh token lifecycle and audit.
5. Usage metering, quotas, rate limits, subscription billing and abuse prevention.
6. AI provider abstraction (Gemini/OpenAI/local), finite budgets and no silent fallback to paid providers.
7. Production plugins: gameplay, tutorials, storytelling; rights and provenance checks.
8. Real uploader with verified privacy states, manual approval and YouTube platform-policy compliance.

## Known limits

This is **not production SaaS**. There is no authenticated API, real tenant-level authorization,
payment processing, background execution, YouTube connection or AI provider built into the new platform layer.
SQLite workspace scoping is a local organizational boundary, not a secure multi-user boundary.
