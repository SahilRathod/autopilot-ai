# YouTube account connection — first V0.6 slice

This feature uses a Google Desktop OAuth client and YouTube Data API v3 to link a real YouTube channel to one existing Autopilot AI channel profile. It is currently Windows-only and read-only.

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

No publishing, uploads, automated engagement, or audience retention analytics are enabled yet. Channel counts come from the actual YouTube API and may be rounded or unavailable. Automated tests mock Google requests. Live Google consent and Windows DPAPI verification require a Windows device and valid Google Cloud configuration.
