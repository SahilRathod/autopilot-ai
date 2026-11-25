'use client';

import {useEffect,useState} from 'react';
import {api} from '../lib/api';

type Upload={job_id:number;video_id:string|null;title:string;state:string};
type Action={id:number;kind:string;video_id:string;publish_at:string|null;state:string;provider_id:string|null};

export default function PublicationPanel({base,remoteTitle}:{base:string;remoteTitle:string}){
  const [uploads,setUploads]=useState<Upload[]>([]);
  const [history,setHistory]=useState<Action[]>([]);
  const [job,setJob]=useState('');
  const [when,setWhen]=useState('');
  const [approved,setApproved]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  async function refresh(){
    const [u,a]=await Promise.all([api<Upload[]>(base+'/uploads'),api<Action[]>(base+'/actions')]);
    setUploads(u);setHistory(a);
  }
  useEffect(()=>{refresh().catch(e=>setError(String(e.message||e)));},[base]);
  const selected=uploads.find(u=>String(u.job_id)===job&&u.state==='uploaded'&&u.video_id);
  const date=when?new Date(when):null;
  const valid=!!date&&!Number.isNaN(date.getTime())&&date.getTime()>=Date.now()+3600000;
  async function schedule(){
    if(!selected||!date||!valid||!approved||busy)return;
    setBusy(true);setError('');setNotice('');
    try{
      await api(base+'/schedule',{method:'POST',body:JSON.stringify({job_id:selected.job_id,publish_at:date.toISOString(),approved:true})});
      setNotice('YouTube confirmed the future publication schedule. This does not mean the video is public yet.');
      setApproved(false);await refresh();
    }catch(e){setError(e instanceof Error?e.message:String(e));await refresh().catch(()=>{});}
    finally{setBusy(false);}
  }
  return <div className="stack-form">
    <h3>Approved publication calendar</h3>
    <p>Schedule an already uploaded, processed private video to become public. YouTube handles the date even when the local laptop is offline. This is a separate public action, not automatic publishing.</p>
    {error&&<div className="notice danger" role="alert">{error}</div>}
    {notice&&<div className="tip" role="status">{notice}</div>}
    <button type="button" className="button outline" disabled={busy} onClick={()=>{setBusy(true);refresh().catch(e=>setError(String(e.message||e))).finally(()=>setBusy(false));}}>Refresh publication history</button>
    <label>Confirmed private upload<select value={job} disabled={busy} onChange={e=>{setJob(e.target.value);setApproved(false);}}>
      <option value="">Select reviewed video</option>
      {uploads.filter(u=>u.state==='uploaded'&&u.video_id).map(u=><option key={u.job_id} value={u.job_id}>{u.title} ({u.video_id})</option>)}
    </select></label>
    {selected&&<p><a href={'https://studio.youtube.com/video/'+selected.video_id+'/edit'} target="_blank" rel="noreferrer">Review the exact video and metadata in YouTube Studio</a></p>}
    <label>Publication time (your browser's local time)<input type="datetime-local" value={when} disabled={busy} onChange={e=>{setWhen(e.target.value);setApproved(false);}}/></label>
    {date&&valid&&<p>Selected: {date.toLocaleString()} · UTC: {date.toISOString()}</p>}
    <small>Choose at least one hour in the future. An existing provider schedule is never overwritten.</small>
    <label><input type="checkbox" checked={approved} disabled={!selected||!valid||busy} onChange={e=>setApproved(e.target.checked)}/> I reviewed this exact video and authorize making it PUBLIC on {remoteTitle} at the selected time.</label>
    <button type="button" className="button primary" disabled={!selected||!valid||!approved||busy} onClick={schedule}>Confirm public publication schedule</button>
    <h3>Remote action history</h3>
    {!history.length&&<p>No remote publication or reply actions yet.</p>}
    {history.map(a=><div className="job-row" key={a.id}><div className="job-main"><strong>{a.kind==='schedule'?'Publication schedule':'Comment reply'} · {a.state}</strong><p>{a.video_id}{a.publish_at?' · '+new Date(a.publish_at).toLocaleString():''}</p><a href={'https://studio.youtube.com/video/'+a.video_id+'/edit'} target="_blank" rel="noreferrer">Verify in YouTube Studio</a></div></div>)}
    <p>Requested or review-required actions may have reached YouTube. Never repeat uncertain actions; verify, cancel or change schedules in YouTube Studio.</p>
  </div>;
}
