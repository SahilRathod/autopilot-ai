'use client';

import {FormEvent,useEffect,useState} from 'react';
import {api} from '../lib/api';

type Export = {job_id:number; quality:string; caption_mode:string};
type Task = {job_id:number;title:string;state:string;file_bytes:number;bytes_uploaded:number;video_id:string|null;error:string|null};

export default function PrivateUploadPanel({workspaceId,channelId,remoteTitle,remoteId}:{
  workspaceId:number;channelId:number;remoteTitle:string;remoteId:string;
}){
  const base='/workspaces/'+workspaceId+'/channels/'+channelId;
  const [files,setFiles]=useState<Export[]>([]);
  const [tasks,setTasks]=useState<Task[]>([]);
  const [job,setJob]=useState<number|null>(null);
  const [title,setTitle]=useState('');
  const [description,setDescription]=useState('');
  const [category,setCategory]=useState('20');
  const [kids,setKids]=useState('');
  const [consent,setConsent]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');

  useEffect(()=>{
    let active=true;let timer:ReturnType<typeof setTimeout>;
    async function poll(){
      try{
        const [exports,uploads]=await Promise.all([api<Export[]>(base+'/media/exports'),api<Task[]>(base+'/youtube/uploads')]);
        if(active){setFiles(exports);setTasks(uploads);}
      }catch(e){if(active)setError(e instanceof Error?e.message:String(e));}
      finally{if(active)timer=setTimeout(poll,4000);}
    }
    void poll();
    return()=>{active=false;clearTimeout(timer);};
  },[base]);

  const eligible=files.filter(f=>!tasks.some(t=>t.job_id===f.job_id));
  const valid=job!==null&&eligible.some(f=>f.job_id===job);
  async function submit(e:FormEvent<HTMLFormElement>){
    e.preventDefault();
    if(!valid||!consent||kids===''||busy)return;
    setBusy(true);setError('');
    try{
      const row=await api<Task>(base+'/youtube/uploads',{method:'POST',body:JSON.stringify({
        job_id:job,title,description,category_id:category,made_for_kids:kids==='yes',private_upload_approved:true
      })});
      setTasks(old=>[row,...old]);setJob(null);setConsent(false);setTitle('');setDescription('');setKids('');
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  async function retry(id:number){
    setBusy(true);setError('');
    try{
      const row=await api<Task>(base+'/youtube/uploads/'+id+'/retry',{method:'POST',body:'{}'});
      setTasks(old=>old.map(t=>t.job_id===id?row:t));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  return <div className="assembly-results stack-form">
    <h2>Private video upload</h2>
    <p>Destination: <strong>{remoteTitle}</strong> · {remoteId}. Nothing is made public.</p>
    {error&&<div className="notice danger" role="alert">{error}</div>}
    <form className="stack-form" onSubmit={submit}>
      <label>Reviewed export<select required value={job??''} disabled={busy}
        onChange={e=>{setJob(e.target.value?Number(e.target.value):null);setConsent(false);}}>
        <option value="">Choose a finished MP4</option>
        {eligible.map(f=><option key={f.job_id} value={f.job_id}>Job #{f.job_id} · {f.quality} · {f.caption_mode} captions</option>)}
      </select></label>
      {!eligible.length&&<p>Finish a new approved assembly export in Media Studio.</p>}
      {valid&&<video key={job} className="media-video" controls preload="metadata"
        src={'/api/v1'+base+'/media/exports/'+job+'/preview'} aria-label="Preview video before private upload"/>}
      <label>Video title<input required maxLength={100} value={title} disabled={busy} onChange={e=>{setTitle(e.target.value);setConsent(false);}}/></label>
      <label>Description<textarea maxLength={5000} rows={5} value={description} disabled={busy} onChange={e=>{setDescription(e.target.value);setConsent(false);}}/></label>
      <label>Category<select value={category} disabled={busy} onChange={e=>{setCategory(e.target.value);setConsent(false);}}>
        <option value="20">Gaming</option><option value="22">People &amp; Blogs</option><option value="24">Entertainment</option>
        <option value="27">Education</option><option value="28">Science &amp; Technology</option>
      </select></label>
      <label>Audience<select required value={kids} disabled={busy} onChange={e=>{setKids(e.target.value);setConsent(false);}}>
        <option value="">Choose the correct audience declaration</option><option value="yes">Yes, made for kids</option><option value="no">No, not made for kids</option>
      </select></label>
      <label><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/> I reviewed this video and metadata, have rights to upload it, and approve sending it privately to {remoteTitle}.</label>
      <button type="submit" className="button primary" disabled={busy||!valid||!title.trim()||!consent||!kids}>Queue private upload</button>
    </form>
    <h3>Upload history and confirmed transfer progress</h3>
    {!tasks.length&&<p>No uploads requested. Keep the local upload worker running.</p>}
    {tasks.map(t=><div key={t.job_id} className="assembly-clip-row">
      <div><strong>{t.title} · {t.state.replaceAll('_',' ')}</strong>
      <p className="media-muted">{t.file_bytes>0?Math.floor(100*t.bytes_uploaded/t.file_bytes):0}% bytes confirmed by Google · Job #{t.job_id}</p>
      {t.error&&<p className="media-muted">{t.error}</p>}
      {t.video_id&&<a href={'https://studio.youtube.com/video/'+t.video_id+'/edit'} target="_blank" rel="noreferrer">Review private video in YouTube Studio</a>}
      </div>
      {(t.state==='failed'||t.state==='interrupted')&&<button type="button" className="button outline" disabled={busy} onClick={()=>retry(t.job_id)}>Retry existing task</button>}
    </div>)}
  </div>;
}
