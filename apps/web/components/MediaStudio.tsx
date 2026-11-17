'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { api, type Channel, type ProductionJob } from '../lib/api';

type Asset = {
  id: number; filename: string; duration_seconds: number; width: number;
  height: number; fps: number; video_codec: string; audio_codec: string | null;
};
type Candidate = {
  id: number; start_seconds: number; duration_seconds: number;
  reason: 'opening_segment' | 'scene_change';
};
type RenderResult = { job_id: number; output_path: string; youtube_uploaded: boolean };
type RankProfile = 'balanced' | 'tactical' | 'sandbox';
type RankedClip = {
  candidate_id: number; score: number; profile: RankProfile; audio_analyzed: boolean;
  audio_score: number; visual_score: number;
  evidence: { signals: { audio_transient: string; visual_transition: boolean };
              reasons: string[]; claims: string };
};
const clock = (value: number) => {
  const secs = Math.max(0, Math.floor(value));
  return Math.floor(secs / 60) + ':' + String(secs % 60).padStart(2, '0');
};

export default function MediaStudio({workspaceId, channels, jobs, onRendered}: {
  workspaceId: number; channels: Channel[]; jobs: ProductionJob[]; onRendered: () => void;
}) {
  const [channelId, setChannelId] = useState<number | null>(channels[0]?.id ?? null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filename, setFilename] = useState('');
  const [clipSeconds, setClipSeconds] = useState(30);
  const [threshold, setThreshold] = useState(0.35);
  const [profile, setProfile] = useState<RankProfile>('balanced');
  const [ranked, setRanked] = useState<RankedClip[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [playerError, setPlayerError] = useState('');
  const player = useRef<HTMLVideoElement>(null);
  const base = channelId === null ? '' : '/workspaces/' + workspaceId + '/channels/' + channelId + '/media';
  const selectedAsset = assets.find(a => a.id === assetId);
  const selected = candidates.find(c => c.id === selectedId);
  const approvedJobs = jobs.filter(j => j.channel_id === channelId && j.state === 'approved');
  const rankingByCandidate = new Map(ranked.map(row => [row.candidate_id, row]));
  const sortedCandidates = [...candidates].sort((a, b) => {
    const left = rankingByCandidate.get(a.id);
    const right = rankingByCandidate.get(b.id);
    return left && right ? right.score - left.score || a.start_seconds - b.start_seconds
      : left ? -1 : right ? 1 : a.start_seconds - b.start_seconds;
  });
  const selectedRanking = selected ? rankingByCandidate.get(selected.id) : undefined;

  useEffect(() => {
    if (!channels.some(c => c.id === channelId)) setChannelId(channels[0]?.id ?? null);
  }, [channels, channelId]);

  useEffect(() => {
    let active = true;
    setAssets([]); setAssetId(null); setCandidates([]); setSelectedId(null);
    setJobId(null); setNotice(''); setError(''); setPlayerError(''); setPreviewing(false); setRanked([]);
    if (base) api<Asset[]>(base + '/assets').then(items => {
      if (active) { setAssets(items); setAssetId(items[0]?.id ?? null); }
    }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [base]);

  useEffect(() => {
    let active = true;
    setCandidates([]); setSelectedId(null); setPreviewing(false); setPlayerError(''); setRanked([]);
    if (base && assetId !== null) {
      api<Candidate[]>(base + '/assets/' + assetId + '/candidates').then(items => {
        if (active) { setCandidates(items); setSelectedId(items[0]?.id ?? null); }
      }).catch(e => { if (active) setError(String(e)); });
    }
    return () => { active = false; };
  }, [base, assetId]);

  useEffect(() => {
    let active = true;
    setRanked([]);
    if (base && assetId !== null) {
      api<RankedClip[]>(base + '/assets/' + assetId + '/rankings?profile=' + profile)
        .then(rows => { if (active) setRanked(rows); })
        .catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)); });
    }
    return () => { active = false; };
  }, [base, assetId, profile]);

  useEffect(() => {
    if (jobId !== null && !approvedJobs.some(j => j.id === jobId)) setJobId(null);
  }, [jobId, approvedJobs]);

  function seek(c: Candidate) {
    setSelectedId(c.id); setPreviewing(false);
    if (player.current) {
      player.current.pause();
      player.current.currentTime = c.start_seconds;
    }
  }

  async function playSelected() {
    if (!selected || !player.current) return;
    const current = player.current;
    current.pause();
    current.currentTime = selected.start_seconds;
    setPlayerError(''); setPreviewing(true);
    try { await current.play(); }
    catch { setPreviewing(false); setPlayerError('Browser could not play this source. Try a compatible H.264 MP4 or WebM.'); }
  }

  function onTimeUpdate() {
    if (previewing && selected && player.current &&
        player.current.currentTime >= selected.start_seconds + selected.duration_seconds) {
      player.current.pause();
      setPreviewing(false);
    }
  }

  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!base || !filename.trim()) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const imported = await api<Asset>(base + '/import', {
        method:'POST', body: JSON.stringify({ filename: filename.trim() }),
      });
      const all = await api<Asset[]>(base + '/assets');
      setAssets(all); setAssetId(imported.id); setFilename('');
      setNotice('Footage registered. The original file has not been changed.');
    } catch(e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function scan() {
    if (!base || assetId === null) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await api(base + '/assets/' + assetId + '/scan', {
        method:'POST', body: JSON.stringify({
          clip_seconds: clipSeconds, threshold, max_scan_seconds: 120,
        }),
      });
      const updated = await api<Candidate[]>(base + '/assets/' + assetId + '/candidates');
      setCandidates(updated); setSelectedId(updated[0]?.id ?? null); setRanked([]);
      setNotice(updated.length + ' visual candidate clips found. Inspect each before rendering.');
    } catch(e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function rankClips() {
    if (!base || assetId === null || !candidates.length) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const results = await api<RankedClip[]>(base + '/assets/' + assetId + '/rank', {
        method: 'POST', body: JSON.stringify({profile, max_seconds: 120}),
      });
      setRanked(results);
      setNotice('Ranked ' + results.length + ' clips using local audio/visual heuristics. Scores are not gameplay-event predictions.');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function render() {
    if (!base || selectedId === null || jobId === null) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api<RenderResult>(base + '/candidates/' + selectedId + '/render', {
        method:'POST', body: JSON.stringify({job_id:jobId}),
      });
      setNotice('Clip rendered for job #' + result.job_id + ' at ' + result.output_path +
                '. Nothing was uploaded to YouTube.');
      setJobId(null);
      onRendered();
    } catch(e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return <div className="media-studio">
    <div className="two-col main-sidebar">
      <section className="panel">
        <div className="panel-heading"><div><h2>Media library</h2>
          <p>Preview original footage saved in the local media/raw directory.</p></div>
          <span className="chip">{assets.length} registered</span>
        </div>
        {error && <div className="notice danger" role="alert">{error}</div>}
        {notice && <div className="notice success" role="status">{notice}</div>}
        {channels.length ? <>
          <label className="media-field">Channel
            <select aria-label="Media channel" value={channelId ?? ''}
              onChange={e => setChannelId(Number(e.target.value))} disabled={busy}>
              {channels.map(ch => <option key={ch.id} value={ch.id}>{ch.name}</option>)}
            </select>
          </label>
          <form className="stack-form" onSubmit={register}>
            <label>Filename inside media/raw/
              <input required maxLength={255} value={filename} placeholder="gameplay.mp4"
                onChange={e => setFilename(e.target.value)} />
            </label>
            <button className="button outline" disabled={busy || !filename.trim()}>
              + Register footage
            </button>
          </form>
          <label className="media-field">Select footage
            <select aria-label="Select video file" value={assetId ?? ''}
              onChange={e => setAssetId(e.target.value ? Number(e.target.value) : null)}
              disabled={busy || !assets.length}>
              {!assets.length && <option value="">No imported files yet</option>}
              {assets.map(a => <option value={a.id} key={a.id}>
                {a.filename} · {clock(a.duration_seconds)}
              </option>)}
            </select>
          </label>
          {selectedAsset && <div className="media-player">
            <div className="media-player-top"><strong>{selectedAsset.filename}</strong>
              <span>{selectedAsset.width}×{selectedAsset.height} · {selectedAsset.fps.toFixed(1)} FPS</span>
            </div>
            <video key={workspaceId + '-' + channelId + '-' + assetId}
              ref={player} className="media-video" controls preload="metadata" playsInline
              onTimeUpdate={onTimeUpdate}
              onError={() => setPlayerError("Unable to play this media in your browser. The local file may be unavailable or use an unsupported codec.")}
              src={'/api/v1' + base + '/assets/' + assetId + '/preview'}
              aria-label={'Preview original video: ' + selectedAsset.filename}>
              Your browser cannot play this video.
            </video>
            {playerError && <p className="media-muted" role="alert">{playerError}</p>}
            <p className="media-muted">
              Codec: {selectedAsset.video_codec} · {selectedAsset.audio_codec || 'no audio'}.
              Browser preview requires a supported MP4/WebM codec.
            </p>
            {candidates.length > 0 && <div className="media-timeline" aria-label="Scene candidate markers">
              {candidates.map(c => <button type="button" key={c.id}
                className={'media-marker ' + (c.id === selectedId ? 'active' : '')}
                style={{left: Math.min(98, c.start_seconds / selectedAsset.duration_seconds * 100) + '%'}}
                title={'Seek to ' + clock(c.start_seconds)}
                aria-label={'Seek to candidate at ' + clock(c.start_seconds)}
                onClick={() => seek(c)}/>)}
            </div>}
          </div>}
        </> : <p>Create a channel first to use the Media Studio.</p>}
      </section>
      <section className="panel">
        <div className="panel-heading"><div><h2>Scene analysis</h2>
          <p>Find visual transitions, then choose a moment manually.</p></div></div>
        <div className="stack-form">
          <label>Clip length in seconds
            <input type="number" min={1} max={120} step={1} value={clipSeconds}
              onChange={e => setClipSeconds(Number(e.target.value))} disabled={busy} />
          </label>
          <label>Scene sensitivity (0.05–0.95)
            <input type="number" min={0.05} max={0.95} step={0.05} value={threshold}
              onChange={e => setThreshold(Number(e.target.value))} disabled={busy} />
          </label>
          <button className="button primary" type="button" onClick={scan}
            disabled={busy || assetId === null || !Number.isFinite(clipSeconds)
              || clipSeconds < 1 || clipSeconds > 120 || !Number.isFinite(threshold)
              || threshold < 0.05 || threshold > 0.95}>
            {busy ? 'Analyzing…' : 'Find candidate clips'}
          </button>
        </div>
        <label className="media-field">Clip-ranking preset
          <select aria-label="Clip-ranking preset" value={profile}
            onChange={e => setProfile(e.target.value as RankProfile)} disabled={busy}>
            <option value="balanced">Balanced · mixed gaming</option>
            <option value="tactical">Tactical action · Valorant / CS-style</option>
            <option value="sandbox">Sandbox exploration · Minecraft-style</option>
          </select>
        </label>
        <button className="button outline" type="button" onClick={rankClips}
          disabled={busy || assetId === null || !candidates.length}>
          {busy ? 'Working…' : 'Rank clips locally'}
        </button>
        <div className="tip">Scanning finds visual transitions. Ranking combines those candidates with
          relative audio-energy spikes and a user-selected preset. No game-specific kills,
          wins, or other events are recognized. The original file stays untouched.</div>
      </section>
    </div>
    {selectedAsset && <section className="panel">
      <div className="panel-heading"><div><h2>Clip candidates</h2>
        <p>Choose and preview potential clips. Scores reflect heuristics, not actual highlight certainty.</p></div>
        <span className="chip">{candidates.length} candidates</span></div>
      {candidates.length ? <div className="media-candidate-grid">
        {sortedCandidates.map((c,i) => <button type="button" key={c.id}
          onClick={() => seek(c)} aria-pressed={c.id === selectedId}
          className={'media-candidate ' + (c.id === selectedId ? 'active' : '')}>
          <span className="media-candidate-index">{String(i+1).padStart(2,'0')}</span>
          <strong>{c.reason === 'opening_segment' ? 'Opening clip' : 'Scene transition'}</strong>
          <small>{clock(c.start_seconds)} – {clock(c.start_seconds+c.duration_seconds)}</small>
          <small>{Math.round(c.duration_seconds)} seconds</small>
          {rankingByCandidate.has(c.id) && <span className="media-rank-score">
            Heuristic score {rankingByCandidate.get(c.id)?.score}/100
          </span>}
        </button>)}
      </div> : <div className="empty-small">Scan the footage to generate potential clips.</div>}
      {selected && <div className="media-review">
        <div><h3>Selected segment</h3>
          <p>{clock(selected.start_seconds)} to {clock(selected.start_seconds + selected.duration_seconds)}.
          Watch the section above before rendering.</p>
        </div>
        {selectedRanking && <div className="media-rank-explanation">
          <strong>Why this clip was recommended · {selectedRanking.score}/100</strong>
          <ul>{selectedRanking.evidence.reasons.map((reason,i) => <li key={i}>{reason}</li>)}</ul>
          <small>Audio: {selectedRanking.evidence.signals.audio_transient}. These are
          visual/audio signals only, not predictions of game events.</small>
        </div>}
        <button className="button outline" type="button" onClick={playSelected}>
          {previewing ? 'Restart selected clip' : 'Play selected clip'}
        </button>
        <div className="media-render-form">
          <label>Approved production job
            <select aria-label="Approved production job" value={jobId ?? ''}
              onChange={e => setJobId(e.target.value ? Number(e.target.value) : null)}
              disabled={busy || !approvedJobs.length}>
              <option value="">Select an approved job</option>
              {approvedJobs.map(j => <option key={j.id} value={j.id}>
                #{j.id} · {j.title} ({j.format})
              </option>)}
            </select>
          </label>
          <button className="button primary" type="button" disabled={busy || jobId === null}
            onClick={render}>{busy ? 'Rendering…' : 'Render reviewed clip'}</button>
        </div>
        {!approvedJobs.length && <p className="media-muted">
          No approved job in this channel. Create one in Production queue, then approve it.
        </p>}
      </div>}
    </section>}
  </div>;
}
