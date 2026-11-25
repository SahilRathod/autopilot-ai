'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import MediaStudio from './MediaStudio';
import YouTubeStudio from './YouTubeStudio';
import { api, type AuditEvent, type Channel, type Overview, type ProductionJob, type Workspace } from '../lib/api';

type Section = 'overview' | 'channels' | 'production' | 'media' | 'youtube' | 'ai' | 'reviews' | 'activity';
const nav: { id: Section; icon: string; label: string }[] = [
  { id: 'overview', icon: '◫', label: 'Overview' },
  { id: 'channels', icon: '▣', label: 'Channels' },
  { id: 'youtube', icon: '▶', label: 'YouTube accounts' },
  { id: 'production', icon: '▤', label: 'Production queue' },
  { id: 'media', icon: '▶', label: 'Media Studio' },
  { id: 'ai', icon: '✦', label: 'AI Director' },
  { id: 'reviews', icon: '✓', label: 'Approval center' },
  { id: 'activity', icon: '◷', label: 'Activity history' },
];
const actions: Record<string, { label: string; next: string; secondary?: boolean }[]> = {
  draft: [{ label: 'Submit for review', next: 'ready_for_review' }, { label: 'Reject', next: 'rejected', secondary: true }],
  ready_for_review: [{ label: 'Approve', next: 'approved' }, { label: 'Reject', next: 'rejected', secondary: true }],
  approved: [{ label: 'Queue locally', next: 'queued' }, { label: 'Reject', next: 'rejected', secondary: true }],
  queued: [{ label: 'Mark complete (local)', next: 'completed' }, { label: 'Mark failed', next: 'failed', secondary: true }],
  failed: [{ label: 'Retry local queue', next: 'queued' }, { label: 'Reject', next: 'rejected', secondary: true }],
};
function displayState(state: string) { return state.replaceAll('_', ' '); }

export default function Studio() {
  const [section, setSection] = useState<Section>('overview');
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState<number | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [jobs, setJobs] = useState<ProductionJob[]>([]);
  const [activity, setActivity] = useState<AuditEvent[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [filterChannel, setFilterChannel] = useState('all');
  const [workspaceName, setWorkspaceName] = useState('');
  const [channelName, setChannelName] = useState('');
  const [channelNiche, setChannelNiche] = useState('gaming');
  const [channelLanguage, setChannelLanguage] = useState('Hinglish');
  const [jobTitle, setJobTitle] = useState('');
  const [jobChannelId, setJobChannelId] = useState('');
  const [jobFormat, setJobFormat] = useState<'short' | 'long'>('short');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const reloadWorkspaces = useCallback(async () => {
    const rows = await api<Workspace[]>('/workspaces');
    setWorkspaces(rows);
    setWorkspaceId(previous => previous && rows.some(w => w.id === previous) ? previous : rows[0]?.id ?? null);
  }, []);

  const reloadCurrent = useCallback(async (id: number) => {
    const [c, j, o, a] = await Promise.all([
      api<Channel[]>(`/workspaces/${id}/channels`),
      api<ProductionJob[]>(`/workspaces/${id}/jobs`),
      api<Overview>(`/workspaces/${id}/overview`),
      api<AuditEvent[]>(`/workspaces/${id}/audit?limit=30`),
    ]);
    setChannels(c); setJobs(j); setOverview(o); setActivity(a);
    setJobChannelId(previous => c.some(channel => String(channel.id) === previous) ? previous : String(c[0]?.id ?? ''));
  }, []);

  useEffect(() => {
    reloadWorkspaces().catch(e => setError(e instanceof Error ? e.message : 'Backend unavailable')).finally(() => setLoading(false));
  }, [reloadWorkspaces]);
  useEffect(() => {
    if (workspaceId === null) { setChannels([]); setJobs([]); setOverview(null); setActivity([]); return; }
    reloadCurrent(workspaceId).catch(e => setError(e instanceof Error ? e.message : 'Cannot load workspace'));
  }, [workspaceId, reloadCurrent]);

  async function change(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(''); setStatus('');
    try {
      await action();
      await reloadWorkspaces();
      if (workspaceId !== null) await reloadCurrent(workspaceId);
      setStatus(success);
    } catch (e) { setError(e instanceof Error ? e.message : 'Operation failed'); }
    finally { setBusy(false); }
  }
  async function addWorkspace(e: FormEvent) {
    e.preventDefault();
    if (!workspaceName.trim()) return;
    await change(async () => {
      const created = await api<Workspace>('/workspaces', { method:'POST', body: JSON.stringify({ name: workspaceName }) });
      setWorkspaceId(created.id); setWorkspaceName('');
    }, 'Workspace created');
  }
  async function addChannel(e: FormEvent) {
    e.preventDefault(); if (workspaceId === null) return;
    await change(async () => {
      await api(`/workspaces/${workspaceId}/channels`, { method:'POST', body: JSON.stringify({ name:channelName, niche:channelNiche, language:channelLanguage }) });
      setChannelName('');
    }, 'Channel added');
  }
  async function addJob(e: FormEvent) {
    e.preventDefault(); if (workspaceId === null || !jobChannelId) return;
    await change(async () => {
      await api(`/workspaces/${workspaceId}/jobs`, { method:'POST', body: JSON.stringify({ channel_id:Number(jobChannelId), title:jobTitle, format:jobFormat }) });
      setJobTitle('');
    }, 'Draft job created');
  }
  async function transition(id: number, next: string) {
    if (workspaceId === null) return;
    await change(() => api(`/workspaces/${workspaceId}/jobs/${id}/transition`, {method:'POST', body:JSON.stringify({to:next})}), 'Job marked ' + displayState(next));
  }
  const activeWorkspace = workspaces.find(w => w.id === workspaceId);
  const filteredJobs = useMemo(() => jobs.filter(j => filterChannel === 'all' || String(j.channel_id) === filterChannel), [jobs, filterChannel]);
  const reviewJobs = filteredJobs.filter(j => ['ready_for_review', 'approved'].includes(j.state));
  const nameOfChannel = (id: number) => channels.find(c => c.id === id)?.name ?? 'Unknown channel';

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">✦</span><span>Autopilot <strong>AI</strong><small>CREATOR STUDIO</small></span></div>
      <div className="workspace-select"><span className="overline">WORKSPACE</span><select aria-label="Select workspace" value={workspaceId ?? ''} onChange={e => { setWorkspaceId(Number(e.target.value)); setFilterChannel('all'); }} disabled={!workspaces.length}>
        {workspaces.length ? workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>) : <option value="">No workspace yet</option>}
      </select></div>
      <p className="overline nav-label">MANAGE</p>
      <nav className="navigation">{nav.map(n => <button className={'nav-item ' + (section === n.id ? 'active':'')} key={n.id} onClick={() => setSection(n.id)}><span className="nav-icon">{n.icon}</span>{n.label}{n.id === 'reviews' && !!overview?.pending_review && <span className="nav-count">{overview.pending_review}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><span className="status-dot"/> LOCAL MODE <span className="version">V0.6.1</span><p>Private uploads require explicit approval. Public publishing is disabled.</p></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs">Studio <span>/</span> {nav.find(n => n.id === section)?.label}</div><div className="top-actions"><span className="chip">₹0 API budget</span><span className="chip muted">{overview?.youtube_connected ? "YouTube linked" : "YouTube disconnected"}</span></div></header>
      <div className="content">
        {error && <div className="notice danger" role="alert">{error} <button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
        {status && <div className="notice success" role="status">{status}<button aria-label="Dismiss message" onClick={() => setStatus('')}>×</button></div>}
        {loading ? <div className="panel empty">Connecting to local backend…</div> : <>
          <div className="page-heading"><div><span className="eyebrow">YOUR CREATOR CONTROL CENTER</span><h1>{section === 'overview' ? `Welcome to ${activeWorkspace?.name ?? 'Autopilot AI'}` : nav.find(n => n.id === section)?.label}</h1><p>{section === 'overview' ? 'Organize channels, draft content and review your production pipeline.' : 'Local production stays on your computer. YouTube data is fetched only with your permission.'}</p></div><button className="button ghost" disabled={busy || workspaceId === null} onClick={() => workspaceId !== null && reloadCurrent(workspaceId).catch(e=>setError(String(e)))}>↻ Refresh</button></div>
          {workspaces.length === 0 ? <div className="panel onboarding"><div className="onboarding-icon">✦</div><h2>Create your first workspace</h2><p>A workspace holds multiple channels and their independent production jobs.</p><form onSubmit={addWorkspace} className="inline-form"><input required maxLength={100} placeholder="e.g. My Creator Studio" value={workspaceName} onChange={e=>setWorkspaceName(e.target.value)}/><button className="button primary" disabled={busy}>Create workspace</button></form></div> : <>
            {section === 'overview' && <>
              <div className="kpi-grid">
                <Metric title="Channels" value={overview?.channels ?? 0} detail="Connected channel profiles" icon="▣"/>
                <Metric title="Content jobs" value={overview?.total_jobs ?? 0} detail="Production records" icon="▤"/>
                <Metric title="Needs approval" value={overview?.pending_review ?? 0} detail="Waiting for your review" icon="✓"/>
                <Metric title="Local queue" value={overview?.queue ?? 0} detail="Not YouTube uploads" icon="◷"/>
              </div>
              <div className="two-col"><section className="panel"><div className="panel-heading"><div><h2>Production pipeline</h2><p>Live status of your locally tracked work</p></div></div>
                <div className="pipeline">{['draft','ready_for_review','approved','queued','completed'].map(state => <div className="pipeline-step" key={state}><span className={'pipeline-number '+state}>{overview?.states[state] ?? 0}</span><small>{displayState(state)}</small></div>)}</div>
                <button className="text-link" onClick={() => setSection('production')}>View all production jobs →</button>
              </section><section className="panel"><div className="panel-heading"><div><h2>Platform readiness</h2><p>Clear status, no simulated analytics</p></div></div><div className="readiness-row"><span className="round-check">✓</span><div><strong>Local workspace engine</strong><small>Ready for channel and job management</small></div></div><div className="readiness-row"><span className="round-check">✓</span><div><strong>AI Director</strong><small>Generate offline or optional Gemini content packs</small></div></div><div className="readiness-row"><span className="round-soon">·</span><div><strong>YouTube publishing</strong><small>Explicit private uploads available; public publishing disabled</small></div></div></section></div>
              <section className="panel"><div className="panel-heading"><div><h2>Recent production</h2><p>Latest video jobs from all your channels</p></div><button className="text-link" onClick={() => setSection('production')}>Manage queue →</button></div><JobList jobs={jobs.slice(0,5)} channelName={nameOfChannel} disabled={busy} onTransition={transition}/></section>
            </>}
            {section === 'youtube' && workspaceId !== null && <YouTubeStudio key={workspaceId} workspaceId={workspaceId} channels={channels} onChanged={() => reloadCurrent(workspaceId).catch(e => setError(String(e)))}/>}
            {section === 'media' && workspaceId !== null && <MediaStudio key={workspaceId} workspaceId={workspaceId} channels={channels} jobs={jobs} onRendered={() => reloadCurrent(workspaceId).catch(e => setError(String(e)))}/>}
            {section === 'ai' && workspaceId !== null && <AIDirector workspaceId={workspaceId} channels={channels} onSubmitted={() => reloadCurrent(workspaceId).catch(e => setError(String(e)))}/>}
            {section === 'channels' && <div className="two-col main-sidebar"><section className="panel"><div className="panel-heading"><div><h2>Your channels</h2><p>Each channel has separate content and budgets</p></div><span className="chip">{channels.length} total</span></div><div className="channel-grid">{channels.length ? channels.map(c => <div className="channel-card" key={c.id}><div className="channel-avatar">{c.name[0].toUpperCase()}</div><div><h3>{c.name}</h3><p>{c.niche} · {c.language}</p><small>₹{c.budget_inr}/month · Publishing disabled</small></div></div>) : <div className="empty-small">No channels yet. Add your first one →</div>}</div></section><section className="panel"><h2>Add a channel</h2><p>Start with gaming, then add any content niche.</p><form className="stack-form" onSubmit={addChannel}><label>Channel name<input required maxLength={100} placeholder="e.g. Gaming Universe" value={channelName} onChange={e=>setChannelName(e.target.value)}/></label><label>Content niche<input required maxLength={80} value={channelNiche} onChange={e=>setChannelNiche(e.target.value)}/></label><label>Language<input required maxLength={40} value={channelLanguage} onChange={e=>setChannelLanguage(e.target.value)}/></label><button className="button primary" disabled={busy}>+ Add channel</button></form></section></div>}
            {section === 'production' && <div className="two-col main-sidebar"><section className="panel"><div className="panel-heading"><div><h2>Production jobs</h2><p>Draft → review → approve → local queue</p></div><select aria-label="Filter by channel" value={filterChannel} onChange={e=>setFilterChannel(e.target.value)}><option value="all">All channels</option>{channels.map(c=><option value={c.id} key={c.id}>{c.name}</option>)}</select></div><JobList jobs={filteredJobs} channelName={nameOfChannel} onTransition={transition} disabled={busy}/></section><section className="panel"><h2>New production job</h2><p>Creates a local draft, not a rendered video.</p><form className="stack-form" onSubmit={addJob}><label>Channel<select required value={jobChannelId} onChange={e=>setJobChannelId(e.target.value)}>{channels.map(c=><option value={c.id} key={c.id}>{c.name}</option>)}</select></label><label>Video title<input required maxLength={200} placeholder="e.g. Valorant Beginner Tips" value={jobTitle} onChange={e=>setJobTitle(e.target.value)}/></label><label>Video format<select value={jobFormat} onChange={e=>setJobFormat(e.target.value as 'short'|'long')}><option value="short">Short / vertical</option><option value="long">Long-form</option></select></label><button className="button primary" disabled={busy || !channels.length}>+ Create draft</button></form><div className="tip">Approved production jobs can render selected scene candidates through Media Studio. Uploads are separate, explicit private actions.</div></section></div>}
            {section === 'reviews' && <section className="panel"><div className="panel-heading"><div><h2>Pending decisions</h2><p>Review work before it can enter the local queue</p></div><span className="chip">{reviewJobs.length} items</span></div><JobList jobs={reviewJobs} channelName={nameOfChannel} disabled={busy} onTransition={transition}/>{workspaceId !== null && <JobContentInspector workspaceId={workspaceId} jobs={reviewJobs}/>}<div className="tip">“Approve” changes local workflow status only. No upload, publication or API spending occurs.</div></section>}
            {section === 'activity' && <section className="panel"><div className="panel-heading"><div><h2>Audit trail</h2><p>Recorded actions in this workspace</p></div><span className="chip">Recent {activity.length}</span></div>{activity.length ? <div className="audit-list">{activity.map(item=><div key={item.id} className="audit-row"><span className="audit-icon">◷</span><div><strong>{displayState(item.action)}</strong><small>{item.channel_id ? `Channel #${item.channel_id}` : 'Workspace'}{item.job_id ? ` · Job #${item.job_id}` : ''}</small></div><time>{item.created_at}</time></div>)}</div> : <div className="empty-small">No activity yet.</div>}</section>}
          </>}
        </>}
        <footer className="footer"><span>Autopilot AI V0.6.1 · Connected creator studio</span><span>Public publishing and SaaS authentication: not enabled</span></footer>
      </div>
    </main>
  </div>;
}

type ContentPack = {
  title: string; hook: string; script: string; description: string;
  outline: string[]; keywords: string[]; shorts: string[]; research_needed: string[];
};
type AIDraft = { id: number; job_id: number | null; provider: string; topic: string;
  format: 'short' | 'long'; cached?: boolean; result: ContentPack };
type AIStatus = { offline_ready: boolean; gemini_configured: boolean; model: string };

function AIDirector({workspaceId, channels, onSubmitted}: {
  workspaceId: number; channels: Channel[]; onSubmitted: () => void;
}) {
  const [channelId, setChannelId] = useState<number | null>(channels[0]?.id ?? null);
  const [topic, setTopic] = useState('');
  const [format, setFormat] = useState<'short'|'long'>('short');
  const [provider, setProvider] = useState<'offline'|'gemini'>('offline');
  const [aiStatus, setAIStatus] = useState<AIStatus|null>(null);
  const [drafts, setDrafts] = useState<AIDraft[]>([]);
  const [activeDraft, setActiveDraft] = useState<AIDraft|null>(null);
  const [tone, setTone] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setChannelId(channels[0]?.id ?? null); setActiveDraft(null);
  }, [workspaceId, channels]);

  const base = channelId === null ? '' : '/workspaces/' + workspaceId +
    '/channels/' + channelId + '/ai';

  const refresh = useCallback(async (path: string) => {
    const [status, saved, notes] = await Promise.all([
      api<AIStatus>(path + '/status'),
      api<AIDraft[]>(path + '/drafts'),
      api<Record<string,string>>(path + '/memory'),
    ]);
    setAIStatus(status); setDrafts(saved); setTone(notes.tone ?? '');
    setActiveDraft(current => saved.find(d => d.id === current?.id) ?? saved[0] ?? null);
  }, []);

  useEffect(() => {
    if (!base) {setAIStatus(null);setDrafts([]);setActiveDraft(null); return;}
    setError('');
    refresh(base).catch(e => setError(e instanceof Error ? e.message : String(e)));
  }, [base, refresh]);

  async function generate(e: FormEvent) {
    e.preventDefault(); if (!base) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const draft = await api<AIDraft>(base + '/generate', {
        method:'POST', body:JSON.stringify({topic,format,provider}),
      });
      setActiveDraft(draft);
      setNotice(draft.cached ? 'Reused cached content pack.' : 'New content pack saved as draft.');
      await refresh(base);
      setActiveDraft(draft);
    } catch(e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  async function saveTone(e: FormEvent) {
    e.preventDefault(); if (!base || !tone.trim()) return;
    setBusy(true); setError('');
    try {
      await api(base + '/memory/tone',{method:'PUT',body:JSON.stringify({value:tone})});
      setNotice('Channel preference saved. New content packs will use it.');
    } catch(e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  async function submit(draft: AIDraft) {
    if (!base) return;
    setBusy(true);setError('');
    try {
      const job = await api<{job_id:number}>(base+'/drafts/'+draft.id+'/submit',{method:'POST'});
      setNotice('Linked to unapproved production job #'+job.job_id+'. Review before queuing.');
      await refresh(base);onSubmitted();
    } catch(e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }

  return <div className="two-col main-sidebar">
    <section className="panel">
      <div className="panel-heading"><div><h2>AI content director</h2>
        <p>Generate channel-specific drafts. Nothing is published automatically.</p></div></div>
      {error && <div role="alert" className="notice danger">{error}</div>}
      {notice && <div role="status" className="notice success">{notice}</div>}
      {!channels.length ? <p>Create a channel first to start drafting.</p> : <>
        <form className="stack-form" onSubmit={generate}>
          <label>Channel<select aria-label="AI channel" value={channelId ?? ''} onChange={e => setChannelId(Number(e.target.value))}>
            {channels.map(ch => <option key={ch.id} value={ch.id}>{ch.name} · {ch.language}</option>)}
          </select></label>
          <label>Topic<input required minLength={3} maxLength={180} placeholder="e.g. Valorant beginner tips" value={topic} onChange={e=>setTopic(e.target.value)}/></label>
          <label>Format<select value={format} onChange={e => setFormat(e.target.value as 'short'|'long')}>
            <option value="short">Short</option><option value="long">Long-form</option>
          </select></label>
          <label>Provider<select value={provider} onChange={e => setProvider(e.target.value as 'offline'|'gemini')}>
            <option value="offline">Offline template · ₹0</option>
            <option value="gemini" disabled={!aiStatus?.gemini_configured}>Gemini · requires verified free-tier project</option>
          </select></label>
          <button className="button primary" disabled={busy || !channelId || !topic.trim()}>{busy ? 'Working…':'Generate draft'}</button>
        </form>
        <div className="tip">Offline mode generates editable templates, not factual research. Gemini availability depends on your project settings.</div>
        <h2>Saved drafts</h2>
        <div className="stack-form">
          <label>Preview saved draft<select aria-label="Select AI draft" value={activeDraft?.id ?? ''} onChange={e=>setActiveDraft(drafts.find(d=>d.id===Number(e.target.value))??null)}>
            <option value="">Choose a draft</option>
            {drafts.map(d=><option key={d.id} value={d.id}>#{d.id} · {d.topic} ({d.format})</option>)}
          </select></label>
        </div>
        {activeDraft && <div className="panel" style={{marginTop:16}}>
          <h2>{activeDraft.result.title}</h2>
          <p>{activeDraft.result.hook}</p>
          <h3>Script / outline</h3>
          <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontFamily:'inherit'}}>{activeDraft.result.script}</pre>
          <h3>Video description</h3><p>{activeDraft.result.description}</p>
          <h3>Keywords</h3><p>{activeDraft.result.keywords.join(', ')}</p>
          <h3>Research checklist</h3><ul>{activeDraft.result.research_needed.map((item,i)=><li key={i}>{item}</li>)}</ul>
          <button className="button primary" disabled={busy || activeDraft.job_id !== null} onClick={()=>submit(activeDraft)}>
            {activeDraft.job_id ? 'Already linked to job #'+activeDraft.job_id : 'Send to production drafts'}
          </button>
        </div>}
      </>}
    </section>
    <section className="panel">
      <h2>Channel memory</h2><p>Preferences are stored per channel and reused in generated content.</p>
      <form onSubmit={saveTone} className="stack-form">
        <label>Writing tone<input maxLength={500} value={tone} onChange={e=>setTone(e.target.value)} placeholder="Friendly Hinglish"/></label>
        <button className="button ghost" disabled={busy || !tone.trim() || !channelId}>Save preference</button>
      </form>
      <div className="tip">Keep secrets and credentials out of channel memory.</div>
      <p>Active model: {aiStatus?.gemini_configured ? aiStatus.model : 'Offline only'}</p>
    </section>
  </div>;
}

function JobContentInspector({workspaceId,jobs}:{workspaceId:number;jobs:ProductionJob[]}) {
  const [jobId,setJobId] = useState('');
  const [content,setContent] = useState<ContentPack|null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  useEffect(()=>{setContent(null);setError('');setJobId('');},[workspaceId]);
  async function inspect() {
    if (!jobId) return;
    setBusy(true);setError('');setContent(null);
    try {
      const detail=await api<{result:ContentPack}>('/workspaces/'+workspaceId+'/jobs/'+jobId+'/content');
      setContent(detail.result);
    } catch(e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  return <div className="panel" style={{marginTop:16}}>
    <h3>Inspect AI source content</h3>
    <p>Read the script and evidence checklist before approving the production job.</p>
    <div className="inline-form">
      <select aria-label="AI job to inspect" value={jobId} onChange={e=>{setJobId(e.target.value);setContent(null);setError('');}}>
        <option value="">Select a job</option>
        {jobs.map(job=><option key={job.id} value={job.id}>#{job.id} · {job.title}</option>)}
      </select>
      <button className="button ghost" disabled={!jobId||busy} onClick={inspect}>View source content</button>
    </div>
    {error && <div role="alert" className="notice danger">{error}</div>}
    {content && <div>
      <h3>{content.title}</h3>
      <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontFamily:'inherit'}}>{content.script}</pre>
      <h3>Evidence to verify</h3>
      <ul>{content.research_needed.map((item,i)=><li key={i}>{item}</li>)}</ul>
    </div>}
  </div>;
}

function Metric({ title, value, detail, icon }: { title: string; value: number; detail: string; icon: string }) {
  return <div className="metric-card"><div className="metric-header"><span>{title}</span><span className="metric-icon">{icon}</span></div><strong>{value}</strong><small>{detail}</small></div>;
}
function JobList({ jobs, channelName, onTransition, disabled }: { jobs: ProductionJob[]; channelName: (id:number)=>string; onTransition:(id:number,next:string)=>void; disabled:boolean }) {
  if (!jobs.length) return <div className="empty-small">No jobs to show. Create a channel and draft to get started.</div>;
  return <div className="job-list">{jobs.map(j=><div className="job-row" key={j.id}><span className="job-format">{j.format === 'short' ? '9:16' : '16:9'}</span><div className="job-main"><h3>{j.title}</h3><p>{channelName(j.channel_id)} · {j.format === 'short' ? 'Short' : 'Long video'} · #{j.id}</p><span className={'state-pill state-'+j.state}>{displayState(j.state)}</span></div><div className="job-actions">{(actions[j.state] ?? []).map(a=><button className={'button small '+(a.secondary?'ghost':'outline')} disabled={disabled} key={a.next} onClick={()=>onTransition(j.id,a.next)}>{a.label}</button>)}</div></div>)}</div>;
}
