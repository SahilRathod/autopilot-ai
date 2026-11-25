"""Local multi-channel foundation. NOT a multi-user SaaS authorization layer.

All records are scoped to workspace/channel; a future API must get workspace ID from
an authenticated session, never from a caller-supplied query parameter alone.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / 'data' / 'platform.sqlite3'
STATES = {
    'draft': {'ready_for_review', 'rejected'},
    'ready_for_review': {'approved', 'rejected'},
    'approved': {'queued', 'rejected'},
    'queued': {'completed', 'failed'},
    'failed': {'queued', 'rejected'},
    'completed': set(),
    'rejected': set(),
}

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:
            yield c
    finally:
        c.close()

def initialize():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            name TEXT NOT NULL, niche TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'Hinglish',
            budget_inr INTEGER NOT NULL DEFAULT 0 CHECK (budget_inr >= 0),
            publishing_enabled INTEGER NOT NULL DEFAULT 0 CHECK (publishing_enabled IN (0,1)),
            profile_json TEXT NOT NULL DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id,name));
        CREATE TABLE IF NOT EXISTS production_jobs (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            title TEXT NOT NULL, format TEXT NOT NULL CHECK (format IN ('short','long')),
            state TEXT NOT NULL DEFAULT 'draft', source_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            channel_id INTEGER, job_id INTEGER, action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_channels_workspace ON channels(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_scope ON production_jobs(workspace_id,channel_id,state);
        ''')

def new_workspace(name):
    if not name.strip(): raise ValueError('Workspace name required')
    with connect() as c:
        return c.execute('INSERT INTO workspaces(name) VALUES(?)',(name.strip(),)).lastrowid

def new_channel(workspace_id,name,niche,language='Hinglish'):
    if not name.strip() or not niche.strip(): raise ValueError('Channel name and niche required')
    with connect() as c:
        if not c.execute('SELECT id FROM workspaces WHERE id=?',(workspace_id,)).fetchone():
            raise ValueError('Workspace not found')
        cur=c.execute('INSERT INTO channels(workspace_id,name,niche,language) VALUES(?,?,?,?)',
                      (workspace_id,name.strip(),niche.strip(),language))
        c.execute('INSERT INTO audit_log(workspace_id,channel_id,action) VALUES(?,?,?)',
                  (workspace_id,cur.lastrowid,'channel_created'))
        return cur.lastrowid

def channels(workspace_id):
    with connect() as c:
        return [dict(x) for x in c.execute('SELECT * FROM channels WHERE workspace_id=? ORDER BY id',(workspace_id,))]

def add_job(workspace_id,channel_id,title,fmt):
    if fmt not in ('short','long'): raise ValueError('Invalid format')
    if not title.strip(): raise ValueError('Title required')
    with connect() as c:
        ch=c.execute('SELECT id FROM channels WHERE id=? AND workspace_id=?',(channel_id,workspace_id)).fetchone()
        if ch is None: raise ValueError('Channel not found in workspace')
        cur=c.execute('INSERT INTO production_jobs(workspace_id,channel_id,title,format) VALUES(?,?,?,?)',
                      (workspace_id,channel_id,title.strip(),fmt))
        c.execute('INSERT INTO audit_log(workspace_id,channel_id,job_id,action) VALUES(?,?,?,?)',
                  (workspace_id,channel_id,cur.lastrowid,'job_created'))
        return cur.lastrowid

def jobs(workspace_id,channel_id=None):
    with connect() as c:
        if channel_id is None:
            rows=c.execute('SELECT * FROM production_jobs WHERE workspace_id=? ORDER BY id DESC',(workspace_id,))
        else:
            rows=c.execute('SELECT * FROM production_jobs WHERE workspace_id=? AND channel_id=? ORDER BY id DESC',
                           (workspace_id,channel_id))
        return [dict(x) for x in rows]

def transition(workspace_id,job_id,target):
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        job=c.execute('SELECT * FROM production_jobs WHERE workspace_id=? AND id=?',(workspace_id,job_id)).fetchone()
        if job is None: raise ValueError('Job not found in workspace')
        if target not in STATES[job['state']]: raise ValueError('Invalid transition %s -> %s' % (job['state'],target))
        # Queued represents local intent, NOT an external upload; permissions remain disabled by default.
        changed = c.execute(
            'UPDATE production_jobs SET state=? WHERE id=? AND workspace_id=? AND state=?',
            (target, job_id, workspace_id, job['state']))
        if changed.rowcount != 1:
            raise ValueError('Job state changed concurrently; refresh before retrying')
        c.execute('INSERT INTO audit_log(workspace_id,channel_id,job_id,action) VALUES(?,?,?,?)',
                  (workspace_id,job['channel_id'],job_id,'state_'+target))

def audit(workspace_id):
    with connect() as c:
        return [dict(x) for x in c.execute('SELECT * FROM audit_log WHERE workspace_id=? ORDER BY id DESC',(workspace_id,))]
