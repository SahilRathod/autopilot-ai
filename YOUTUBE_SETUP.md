# YouTube account connection — first V0.6 slice

This feature uses a Google Desktop OAuth client and YouTube Data API v3 to link a real YouTube channel to one existing Autopilot AI channel profile. It is currently Windows-only. Read-only is the default; upload access requires a separate opt-in.

1. Open https://console.cloud.google.com/ and create or select a project.
2. Enable YouTube Data API v3 in APIs & Services.
3. Configure Google Auth Platform branding/audience. If the app is External and in Testing, add your Google account as a test user. Use your own account and follow Google's OAuth policies.
4. Create an OAuth client of type Desktop app. Download the client JSON. Save it as data/youtube-client.json in the repository root (the data directory is ignored by Git). Do not commit it, paste it into chat or share it.
5. Start the app with .\start.ps1. The backend must bind to 127.0.0.1 and have access logging disabled. For manual startup, use uvicorn --host 127.0.0.1 --port 8000 --no-access-log; if using another port, set AUTOPILOT_API_PORT accordingly.
6. In the dashboard create a local channel in Channels, then open YouTube accounts and select the local channel profile.
7. Click Connect YouTube, then the Google authorization link. Choose your intended channel identity and approve the read-only scope. Return after the callback page says Connection successful and click Check connection.
8. Verify the YouTube channel ID and title. Refresh statistics on demand. Disconnect explicitly revokes the Google token before deleting the local link.

A refresh credential is encrypted with Windows DPAPI for the current user, stored only as encrypted bytes in SQLite. OAuth client configuration is local; access tokens are used transiently. Backup copies contain encrypted credentials and should still be protected. The OAuth callback is bound to a single-use expiring PKCE state. Restarting the backend discards incomplete authorizations. The backend is unauthenticated and intended only for trusted local loopback usage, not a public SaaS service.

Google can revoke or expire refresh tokens (including External Testing mode). If refresh fails, inspect your Google account permissions. Revocation can affect grants for the same account and application. A disconnected/expired authorization does not stop local media production. The first slice expects one channel returned by Google's authorized mine=true lookup; ambiguous multiple-channel responses are refused rather than silently linking the wrong channel.

Unattended publishing and automatic engagement are not enabled. Channel counts come from the actual YouTube API and may be rounded or unavailable. Automated tests mock Google requests. Live Google consent and Windows DPAPI verification require a Windows device and valid Google Cloud configuration.

If Google revocation fails or the original credential cannot be unlocked, confirm and use Forget local connection only. It deletes the local encrypted credential and profile, not the Google grant. Remove that grant separately in https://myaccount.google.com/connections. Windows CI tests real DPAPI encryption/decryption using a synthetic credential.


## Private video uploads

1. Connect a read-only channel and verify its ID. Click Authorize private uploads and consent to upload permission for the same channel. Return and check authorization.
2. Produce an approved assembly MP4 in Media Studio. Only finished, scoped assembly exports are eligible; older legacy single-clip files are not supported by this upload path.
3. In YouTube accounts select the reviewed export, enter the title, description, category and the actual made-for-kids designation. Preview the exact video. Explicitly approve private upload to the displayed remote channel.
4. The launcher starts a fourth terminal: the YouTube upload worker. For manual startup run .\.venv\Scripts\python.exe -m app.youtube_upload. The worker does no network upload until you explicitly queue a task.
5. Monitor confirmed uploaded bytes and status. An uploaded result includes the actual YouTube video ID. YouTube processing may still be pending; review the private video in YouTube Studio. An explicitly approved future public schedule is available with optional management permission.

The upload uses 8 MiB resumable chunks, a persisted encrypted session URI, a SHA-256 fingerprint, a per-database worker lock, and explicit approval. A lost response resumes the same session on retry. If the session expires or Google does not confirm the expected private video identity, the task becomes review_required; check YouTube Studio before attempting any new upload. Never create a duplicate upload just because a network response was lost. Uploads default to private and subscriber notification is disabled. A retry requires the original linked channel; no automatic cross-channel fallback.

API quota, Google's consent restrictions, channel eligibility and processing times may prevent uploads. All automated integration tests use synthetic data and mocked Google responses. Live account consent and an actual private upload still must be verified on the creator's Windows machine.

Pending uploads can be cancelled before the worker claims them. Cancellation does not delete any existing remote video or undo bytes already sent during a previously interrupted attempt. Active transfers cannot yet be cancelled from the UI.


## V0.8 channel insights

After linking a channel, select **Fetch latest video performance** to fetch up to 50 accessible uploads and their actual lifetime view/like/comment counts. Unavailable metrics remain unavailable; they are not replaced with zero. The comment review screen loads up to 50 top-level comments on a video owned by that linked channel; reply drafts remain local to the screen. Use YouTube Studio to post a reviewed reply, or the optional management-authorized individual reply action.

For watch time and average percentage viewed, enable **YouTube Analytics API** in the same Google Cloud project, choose **Authorize read-only analytics**, and consent to the new scope. Select the same channel. The app requests a 28-day period ending yesterday UTC; Google may omit recent days due to reporting delays. Existing upload permission must also remain granted if already enabled. Reports and comments are fetched on demand and not persisted in SQLite.

No live Google account authorization or actual private upload has been tested in automated CI. Review actual metrics and provider permissions on Windows.


## V0.9 approved publication and comment management

The separate **Authorize publication and comment management** button requests Google's broad youtube.force-ssl scope. Google may describe this as permission to edit and delete videos/comments; Autopilot AI does not implement deletion or bulk engagement. Existing grants must remain authorized.

For a public schedule, select a confirmed private upload, open it in YouTube Studio to inspect the final video/metadata, and choose a timezone-aware publication time at least one hour ahead. Explicitly approve the exact video and time. The API requires the linked owner, processed private video, matching audience declaration and no existing schedule. It sends a single request to YouTube and verifies the provider response. A confirmed schedule is not a claim the video is already public. YouTube handles the schedule; manage changes/cancellations in YouTube Studio.

For replies, review a top-level comment on an owned video, enter your own exact text, select that comment and explicitly approve posting. No bulk replies or autonomous engagement. The app records requested and confirmed actions. If a request is ambiguous, verify on YouTube Studio; it will not automatically repeat the mutation.

These integrations are tested against mocked API responses only. Verify real OAuth, video processing, and scheduling in a test channel before using production content.
