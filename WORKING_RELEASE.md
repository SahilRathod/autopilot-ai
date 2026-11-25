# V0.5.1 — Working-product release (local render reliability)

This is an incremental release, not a full YouTube automation platform. It preserves V0.5 footage, SQLite records and the existing synchronous API/CLI. New dashboard assemblies are saved in the durable local queue and run by a separate worker, one at a time. No new paid dependencies or automatic uploads.

## Windows daily use

Stop the old frontend and backend terminals before updating. Use the existing cloned repository root and the existing Python virtual environment.

    git status

Before upgrading from an older version, stop all processes and copy data/platform.sqlite3 and data/agent.sqlite3 if present to a safe folder outside the repo. Keep original media and output files too; the SQLite backup does not contain them.

After the verified branch is merged, pull master and run:

    git pull --ff-only origin master
    .\.venv\Scripts\python.exe -m app.maintenance doctor
    .\start.ps1

The launcher checks PATH and dependencies, backs up existing databases, builds the production dashboard, and opens three PowerShell windows: FastAPI (8000), worker, Next.js (3000). If script execution is restricted, run PowerShell with -ExecutionPolicy RemoteSigned -File .\start.ps1, only after reviewing the local script.

Alternatively run these commands in three terminals:

    .\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
    .\.venv\Scripts\python.exe -m app.render_queue
    cd apps\web
    npm.cmd run dev

Open http://127.0.0.1:3000. In Media Studio, select candidates, create/approve a job, choose export options, then Queue local MP4. Render tasks & exports displays pending, running, ready, failed or interrupted. The queue survives closing the dashboard. If no worker is running, tasks remain pending; start the worker to process them.

Queued outputs are checked with FFprobe for expected H.264/AAC streams, resolution, duration and soft subtitle track. The original footage is rechecked at render time. Retry a failed task only after correcting the cause. A stale candidate after a rescan may require a new job; do not rescan or replace selected footage while a task is queued.

## Recovery boundary

The worker uses a per-database OS file lock. If the worker crashes, on its next start it reconciles a committed ready export or marks the task interrupted. Retry is allowed if no unresolved encoder claim exists. If an interrupted task has a rendering assembly claim, the app intentionally refuses automatic retry because an orphan FFmpeg process might still be writing. Stop all render processes and inspect the output before repairing that claim; do not blindly delete database rows. Fully automatic crash cleanup and export versioning are not yet implemented.

The dashboard uses task states, not fabricated percentages. The legacy production job state remains unchanged; queued assembly tasks do not mean a video was published. Legacy single-clip and synchronous assembly endpoints still exist; never use both paths for the same job.

## Isolated development

Create a separate worktree/branch with its own virtual environment, node_modules, data and media:

    git worktree add -b dev/next ..\autopilot-ai-dev master

In the development checkout, install its dependencies and use .\start.ps1 -Dev (3001/8001). Never copy production credentials or database files into development. AUTOPILOT_API_PORT configures the Next.js rewrite; build and start must use the same value.

## Verification

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

CI installs FFmpeg/FFprobe so real integration tests are not intentionally skipped. TypeScript and the Next.js build remain required. Real Windows startup, production footage, sustained render performance, UI browser interactions, YouTube OAuth/private upload, full migrations and automatic recovery of ambiguous interrupted encodes still require work.
