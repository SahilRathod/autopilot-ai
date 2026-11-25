'use client';

import {useEffect, useState} from 'react';
import {api} from '../lib/api';

type Task = {job_id: number; state: 'pending'|'running'|'ready'|'failed'|'interrupted';
  attempts: number; error: string|null};
type Export = {job_id: number; quality: string; caption_mode: string};
export default function RenderQueuePanel({workspaceId, channelId}: {
  workspaceId: number; channelId: number;
}) {
  const base = '/workspaces/' + workspaceId + '/channels/' + channelId + '/media';
  const [tasks, setTasks] = useState<Task[]>([]);
  const [exports, setExports] = useState<Export[]>([]);
  const [preview, setPreview] = useState<number|null>(null);
  const [error, setError] = useState('');
  const [retrying, setRetrying] = useState<number|null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [rows, files] = await Promise.all([
          api<Task[]>(base + '/render-tasks'), api<Export[]>(base + '/exports')
        ]);
        if (active) {
          setTasks(rows); setExports(files); setError('');
          setPreview(current => files.some(f => f.job_id === current) ? current : files[0]?.job_id ?? null);
        }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : String(e)); }
      finally { if (active) timer = setTimeout(poll, 3000); }
    }
    void poll();
    return () => {active = false; clearTimeout(timer);};
  }, [base]);

  async function retry(job: number) {
    setRetrying(job);
    try {
      const result = await api<Task>(base + '/render-tasks/' + job + '/retry', {method: 'POST'});
      setTasks(old => old.map(t => t.job_id === job ? result : t));
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setRetrying(null);}
  }

  return <section className="panel assembly-studio">
    <div className="panel-heading"><div><h2>Render tasks &amp; exports</h2>
      <p>Saved local tasks survive page reloads. Keep the separate render worker running.</p>
    </div><span className="chip">{tasks.filter(t => t.state === 'pending' || t.state === 'running').length} active</span></div>
    {error && <div className="notice danger" role="alert">{error}</div>}
    {!tasks.length && <p>No queued assembly tasks yet.</p>}
    {tasks.map(task => <div className="assembly-clip-row" key={task.job_id}>
      <div><strong>Job #{task.job_id} · {task.state}</strong>
        <p className="media-muted">Attempts: {task.attempts}{task.error ? ' · ' + task.error : ''}</p></div>
      {(task.state === 'failed' || task.state === 'interrupted') &&
        <button type="button" className="button outline" disabled={retrying !== null}
          onClick={() => retry(task.job_id)}>Retry</button>}
    </div>)}
    {!!exports.length && <div className="assembly-results">
      <h3>Finished local videos</h3>
      <label>Choose an export
        <select value={preview ?? ''} onChange={e => setPreview(Number(e.target.value))}>
          {exports.map(f => <option key={f.job_id} value={f.job_id}>
            Job #{f.job_id} · {f.quality} · {f.caption_mode} captions
          </option>)}
        </select>
      </label>
      {preview !== null && <video key={preview} className="media-video" controls preload="metadata"
        src={'/api/v1' + base + '/exports/' + preview + '/preview'}
        aria-label={'Preview finished export for job ' + preview}/>}
      <p className="media-muted">Files are saved in media/output/. No YouTube uploads.</p>
    </div>}
  </section>;
}
