import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / 'data' / 'agent.sqlite3'


def connection():
    DB.parent.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          game TEXT NOT NULL,
          title TEXT NOT NULL,
          format TEXT NOT NULL CHECK(format IN ('short', 'long')),
          state TEXT NOT NULL DEFAULT 'draft',
          source_path TEXT,
          output_path TEXT,
          approved_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER,
          action TEXT NOT NULL, detail TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")


def event(conn, job_id, action, detail=''):
    conn.execute('INSERT INTO events(job_id, action, detail) VALUES(?,?,?)', (job_id, action, detail))


def create(game,title,fmt,source=None):
    if fmt not in {'short','long'}: raise ValueError('format must be short or long')
    with connection() as conn:
        cur=conn.execute('INSERT INTO jobs(game,title,format,source_path) VALUES(?,?,?,?)', (game,title,fmt,source))
        event(conn,cur.lastrowid,'created')
        return cur.lastrowid


def jobs():
    with connection() as conn: return [dict(x) for x in conn.execute('SELECT * FROM jobs ORDER BY id DESC')]


def get(job_id):
    with connection() as conn:
        row=conn.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row is None: raise ValueError('Job not found')
        return dict(row)


def update_state(job_id, state, output=None):
    allowed={'draft': {'rendered','rejected'}, 'rendered':{'approved','rejected'}, 'approved':{'scheduled','rejected'}, 'scheduled':set(), 'rejected':set()}
    with connection() as conn:
        row=conn.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row is None: raise ValueError('Job not found')
        if state not in allowed[row['state']]: raise ValueError(f"Invalid transition: {row['state']} -> {state}")
        conn.execute("""UPDATE jobs SET state=?, output_path=COALESCE(?,output_path),
          approved_at=CASE WHEN ?='approved' THEN CURRENT_TIMESTAMP ELSE approved_at END WHERE id=?""",(state,output,state,job_id))
        event(conn,job_id,state,output or '')
