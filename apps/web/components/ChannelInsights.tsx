'use client';

import {useEffect,useState} from 'react';
import {api} from '../lib/api';

type Video={id:string;title:string;published_at:string|null;privacy:string|null;views:string|null;likes:string|null;comments:string|null;duration:string|null};
type Snapshot={fetched_at:string;channel:{id:string;title:string;subscribers:string|null;views:string|null;public_videos:string|null};videos:Video[];more_uploads:boolean};
type Report={start_date:string;end_date:string;fetched_at:string;metrics:Record<string,number|null>};
type Comment={id:string;text:string;author:string;likes:number|null;published_at:string|null;replies:number|null};
const labels:Record<string,string>={views:'Views',estimatedMinutesWatched:'Watch time (minutes)',averageViewDuration:'Average view duration (seconds)',averageViewPercentage:'Average viewed (%)',subscribersGained:'Subscribers gained',subscribersLost:'Subscribers lost'};
const show=(value:string|number|null|undefined)=>value==null?'Unavailable':String(value);

export default function ChannelInsights({base,authorized}:{base:string;authorized:boolean}){
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [report,setReport]=useState<Report|null>(null);
  const [comments,setComments]=useState<Comment[]|null>(null);
  const [selected,setSelected]=useState<Video|null>(null);
  const [draft,setDraft]=useState('');
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{setSnapshot(null);setReport(null);setComments(null);setSelected(null);setDraft('');setError('');},[base]);
  async function load(kind:'snapshot'|'report'|'comments',video?:Video){
    if(busy)return;
    setBusy(true);setError('');
    try{
      if(kind==='snapshot'){setSnapshot(await api<Snapshot>(base+'/insights'));setSelected(null);setComments(null);setDraft('');}
      else if(kind==='report'){setReport(null);setReport(await api<Report>(base+'/insights/report'));}
      else if(video){setSelected(video);setComments(null);setDraft('');setComments(await api<Comment[]>(base+'/insights/videos/'+encodeURIComponent(video.id)+'/comments'));}
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  return <div className="stack-form">
    <h3>Channel insights</h3>
    <p>Actual YouTube metrics, fetched only on request. No synthetic numbers or automatic comments.</p>
    {error&&<div className="notice danger" role="alert">{error}</div>}
    <button type="button" className="button outline" disabled={busy} onClick={()=>load('snapshot')}>Fetch latest video performance</button>
    {snapshot&&<>
      <p>Fetched {new Date(snapshot.fetched_at).toLocaleString()} · {snapshot.channel.title}</p>
      <p>Subscribers: {show(snapshot.channel.subscribers)} · Channel views: {show(snapshot.channel.views)} · Public videos: {show(snapshot.channel.public_videos)}</p>
      <p>Latest accessible uploads (maximum 50). Video views are lifetime counts, not a period report.</p>
      {snapshot.more_uploads&&<small>More uploads exist; this view is limited to the most recent page.</small>}
      {!snapshot.videos.length&&<p>No accessible uploads returned.</p>}
      {snapshot.videos.map(v=><div className="job-row" key={v.id}><div className="job-main"><h3>{v.title}</h3><p>{show(v.privacy)} · {show(v.views)} views · {show(v.likes)} likes · {show(v.comments)} comments</p><p>{v.published_at?new Date(v.published_at).toLocaleDateString():''}</p><a href={'https://studio.youtube.com/video/'+v.id+'/edit'} target="_blank" rel="noreferrer">Open in YouTube Studio</a></div><button type="button" className="button outline small" disabled={busy} onClick={()=>load('comments',v)}>Review comments</button></div>)}
    </>}
    <h3>28-day analytics report</h3>
    <p>Watch time, average view duration, average percentage viewed and subscriber changes require separate read-only analytics authorization. Google may report data with a delay.</p>
    <button type="button" className="button outline" disabled={busy||!authorized} onClick={()=>load('report')}>Fetch analytics report</button>
    {report&&<><p>Requested dates: {report.start_date} to {report.end_date}</p><div className="two-col">{Object.entries(labels).map(([key,label])=><div key={key}><small>{label}</small><p><strong>{show(report.metrics[key])}</strong></p></div>)}</div></>}
    {selected&&<><h3>Recent comments: {selected.title}</h3>{comments?.length===0&&<p>No visible comments returned.</p>}{comments?.map(c=><div className="job-row" key={c.id}><div className="job-main"><strong>{c.author}</strong><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.text}</p><small>{show(c.likes)} likes · {show(c.replies)} replies</small></div></div>)}
      <label>Optional reply draft (not sent)<textarea rows={3} maxLength={10000} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Write and review your own reply…"/></label>
      <p>Copy your draft into <a href={'https://studio.youtube.com/video/'+selected.id+'/comments'} target="_blank" rel="noreferrer">YouTube Studio</a> to respond manually.</p></>}
  </div>;
}
