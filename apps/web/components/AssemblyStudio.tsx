'use client';

import { FormEvent, useEffect, useState } from 'react';
import { api, type ProductionJob } from '../lib/api';

type Clip = { id: number; start_seconds: number; duration_seconds: number; reason: string };
type ExportResult = { job_id: number; state: string };
const clock = (value: number) => {
  const time = Math.max(0, Math.floor(value));
  return Math.floor(time / 60) + ':' + String(time % 60).padStart(2, '0');
};

export default function AssemblyStudio({workspaceId, channelId, candidates, jobs}: {
  workspaceId: number; channelId: number; candidates: Clip[]; jobs: ProductionJob[];
}) {
  const [selection, setSelection] = useState<number[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [quality, setQuality] = useState<'fast' | 'high'>('fast');
  const [audioMode, setAudioMode] = useState<'preserve' | 'normalize' | 'mute'>('preserve');
  const [captionMode, setCaptionMode] = useState<'none' | 'soft' | 'burn'>('none');
  const [captionText, setCaptionText] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const base = '/workspaces/' + workspaceId + '/channels/' + channelId + '/media';


  useEffect(() => {
    setSelection(current => current.filter(id => candidates.some(c => c.id === id)));
  }, [candidates]);
  useEffect(() => {
    if (jobId !== null && !jobs.some(job => job.id === jobId)) setJobId(null);
  }, [jobs, jobId]);

  function toggle(id: number, checked: boolean) {
    setSelection(current => checked
      ? current.includes(id) || current.length >= 8 ? current : [...current, id]
      : current.filter(x => x !== id));
  }

  function move(id: number, offset: number) {
    setSelection(current => {
      const from = current.indexOf(id), to = from + offset;
      if (from < 0 || to < 0 || to >= current.length) return current;
      const next = [...current];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });
  }

  async function assemble(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (jobId === null || !selection.length || busy) return;
    const lines = captionMode === 'none' ? []
      : captionText.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (captionMode !== 'none' && !lines.length) {
      setError('Add at least one caption line or disable captions.');
      return;
    }
    setError(''); setNotice(''); setBusy(true);
    try {
      const result = await api<ExportResult>(base + '/render-tasks', {
        method: 'POST',
        body: JSON.stringify({job_id: jobId, candidate_ids: selection,
          quality, audio_mode: audioMode, caption_mode: captionMode, caption_lines: lines}),
      });
      setNotice('Job #' + result.job_id + ' saved to the local render queue. Check Render tasks for progress.');
      setJobId(null);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  const total = selection.reduce((sum,id) =>
    sum + (candidates.find(c => c.id === id)?.duration_seconds ?? 0), 0);
  const activeJob = jobs.find(job => job.id === jobId);
  const max = activeJob?.format === 'short' ? 180 : 1800;

  return <section className="panel assembly-studio">
    <div className="panel-heading"><div>
      <h2>Draft video assembly</h2>
      <p>Combine selected clips into one local MP4. Captions come from text you write, not speech transcription.</p>
    </div><span className="chip">Milestone 4</span></div>
    {error && <div className="notice danger" role="alert">{error}</div>}
    {notice && <div className="notice success" role="status">{notice}</div>}
    <div className="two-col main-sidebar">
      <div className="stack-form">
        <h3>1. Choose clips in playback order</h3>
        <div className="assembly-clip-list">
          {candidates.map(c => {
            const index = selection.indexOf(c.id), checked = index !== -1;
            return <div className="assembly-clip-row" key={c.id}>
              <label><input type="checkbox" checked={checked}
                disabled={busy || (!checked && selection.length >= 8)}
                onChange={e => toggle(c.id, e.target.checked)} />
                <span>{clock(c.start_seconds)}–{clock(c.start_seconds + c.duration_seconds)}</span>
                <small>{c.reason === 'scene_change' ? 'Scene transition' : 'Opening clip'}</small>
              </label>
              {checked && <div className="assembly-order">
                <span>#{index + 1}</span>
                <button className="button small ghost" type="button"
                  aria-label={'Move clip ' + c.id + ' earlier'}
                  disabled={busy || index === 0} onClick={() => move(c.id,-1)}>↑</button>
                <button className="button small ghost" type="button"
                  aria-label={'Move clip ' + c.id + ' later'}
                  disabled={busy || index === selection.length - 1}
                  onClick={() => move(c.id,1)}>↓</button>
              </div>}
            </div>;
          })}
        </div>
        <p className="media-muted">{selection.length} clips · {clock(total)} total.
          Shorts limit: 3 minutes. Long-form limit: 30 minutes.</p>
        <h3>2. Choose an approved job</h3>
        <label>Production job
          <select aria-label="Approved assembly job" value={jobId ?? ''}
            onChange={e => setJobId(e.target.value ? Number(e.target.value) : null)}
            disabled={busy || !jobs.length}>
            <option value="">Choose approved production job</option>
            {jobs.map(job => <option key={job.id} value={job.id}>#{job.id} · {job.title} ({job.format})</option>)}
          </select>
        </label>
        {!jobs.length && <p className="media-muted">Approve a job in Production queue before exporting.</p>}
      </div>
      <form className="stack-form" onSubmit={assemble}>
        <h3>3. Configure export</h3>
        <label>Output quality
          <select aria-label="Output quality" value={quality} disabled={busy}
            onChange={e => setQuality(e.target.value as 'fast'|'high')}>
            <option value="fast">Fast · 720p landscape / 720×1280 portrait</option>
            <option value="high">High · 1080p landscape / 1080×1920 portrait</option>
          </select>
        </label>
        <label>Audio handling
          <select aria-label="Audio handling" value={audioMode} disabled={busy}
            onChange={e => setAudioMode(e.target.value as 'preserve'|'normalize'|'mute')}>
            <option value="preserve">Keep original audio</option>
            <option value="normalize">Normalize audio volume</option>
            <option value="mute">Mute (silent soundtrack)</option>
          </select>
        </label>
        <label>Captions
          <select aria-label="Caption delivery" value={captionMode} disabled={busy}
            onChange={e => setCaptionMode(e.target.value as 'none'|'soft'|'burn')}>
            <option value="none">No captions</option>
            <option value="soft">Switchable MP4 subtitle track</option>
            <option value="burn">Visible on video (requires FFmpeg libass)</option>
          </select>
        </label>
        {captionMode !== 'none' && <label>Caption text · one line per card
          <textarea value={captionText} rows={5} maxLength={5000} disabled={busy}
            placeholder={'Welcome to today’s game!\nHere is the best moment.'}
            onChange={e => setCaptionText(e.target.value)} />
          <small>Text cards are spaced evenly, not automatically matched to speech. Review timing.</small>
        </label>}
        <button className="button primary" type="submit"
          disabled={busy || selection.length === 0 || jobId === null || total <= 0 || total > max}>
          {busy ? 'Submitting…' : 'Queue local MP4'}
        </button>
        <p className="media-muted">The separate local render worker processes saved tasks. You can leave this screen while it runs. Nothing is uploaded.</p>
      </form>
    </div>
  </section>;
}
