'use client';
import {FormEvent,useEffect,useState} from 'react';
import {api,type Channel,type ProductionJob} from '../lib/api';
import DraftContentEditor from './DraftContentEditor';
type Asset={id:number;filename:string};
type Task={id:number;topic:string;format:string;due_at:string;state:string;job_id:number|null;candidate_ids:number[];error:string|null};
type Content={draft_id:number;result:{title:string;hook:string;script:string;description:string;research_needed:string[]}};
export default function PlannerStudio({workspaceId,channels,onReview}:{workspaceId:number;channels:Channel[];onReview:()=>void}){
  const [selected,setSelected]=useState<number|null>(channels[0]?.id??null);
  const channel=channels.some(c=>c.id===selected)?selected:channels[0]?.id??null;
  const base=channel===null?'':'/workspaces/'+workspaceId+'/channels/'+channel;
  const [assets,setAssets]=useState<Asset[]>([]),[tasks,setTasks]=useState<Task[]>([]),[jobs,setJobs]=useState<ProductionJob[]>([]);
  const [topic,setTopic]=useState(''),[format,setFormat]=useState('short'),[due,setDue]=useState(''),[asset,setAsset]=useState('');
  const [content,setContent]=useState<Content|null>(null),[inspected,setInspected]=useState<number|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  useEffect(()=>{
    let active=true;let timer:ReturnType<typeof setTimeout>;
    setAssets([]);setTasks([]);setAsset('');setContent(null);setInspected(null);
    if(!base)return;
    async function poll(){
      try{
        const [a,t,j]=await Promise.all([api<Asset[]>(base+'/media/assets'),api<Task[]>(base+'/operator/tasks'),api<ProductionJob[]>('/workspaces/'+workspaceId+'/jobs')]);
        if(active){setAssets(a);setTasks(t);setJobs(j);}
      }catch(e){if(active)setError(e instanceof Error?e.message:String(e));}
      finally{if(active)timer=setTimeout(poll,4000);}
    }
    void poll();return()=>{active=false;clearTimeout(timer);};
  },[base,workspaceId]);
  async function schedule(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(!base)return;setBusy(true);setError('');setNotice('');
    try{
      const task=await api<Task>(base+'/operator/tasks',{method:'POST',body:JSON.stringify({topic,format,due_at:due?new Date(due).toISOString():null,asset_id:asset?Number(asset):null,profile:'balanced',scan_seconds:120,clip_seconds:20})});
      setTasks(old=>[task,...old]);setTopic('');setDue('');setNotice('Task saved. The local worker prepares it when due and idle.');
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function change(task:Task,action:'cancel'|'retry'|'render'){
    setBusy(true);setError('');setNotice('');
    try{await api(base+'/operator/tasks/'+task.id+'/'+action,{method:'POST',body:'{}'});setNotice(action==='render'?'Reviewed montage queued locally.':'Task updated.');setTasks(await api<Task[]>(base+'/operator/tasks'));}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function inspect(job:number){setBusy(true);setError('');try{setContent(await api<Content>('/workspaces/'+workspaceId+'/jobs/'+job+'/content'));setInspected(job);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="two-col main-sidebar">
    <section className="panel stack-form"><h2>Schedule local production</h2><p>Prepare drafts and optional montage suggestions. No automatic publishing.</p>
    {error&&<div className="notice danger" role="alert">{error}</div>}{notice&&<div className="notice success" role="status">{notice}</div>}
    {!channels.length?<p>Create a channel first.</p>:<form className="stack-form" onSubmit={schedule}>
      <label>Channel<select value={channel??''} disabled={busy} onChange={e=>setSelected(Number(e.target.value))}>{channels.map(c=><option value={c.id} key={c.id}>{c.name}</option>)}</select></label>
      <label>Topic<input required minLength={3} maxLength={180} value={topic} onChange={e=>setTopic(e.target.value)}/></label>
      <label>Format<select value={format} onChange={e=>setFormat(e.target.value)}><option value="short">Short</option><option value="long">Long-form</option></select></label>
      <label>Prepare at (local time; blank means now)<input type="datetime-local" value={due} onChange={e=>setDue(e.target.value)}/></label>
      <label>Registered footage<select value={asset} onChange={e=>setAsset(e.target.value)}><option value="">Draft content only</option>{assets.map(a=><option key={a.id} value={a.id}>{a.filename}</option>)}</select></label>
      <p>Optional footage uses existing scene candidates or a bounded initial scan, then heuristic ranking.</p>
      <button className="button primary" disabled={busy||!topic.trim()}>Save scheduled task</button>
    </form>}</section>
    <section className="panel stack-form"><h2>Content calendar</h2>{!tasks.length&&<p>No scheduled tasks yet.</p>}
    {tasks.map(t=>{const job=jobs.find(j=>j.id===t.job_id);return <div className="assembly-clip-row" key={t.id}><div style={{minWidth:0}}>
      <strong>{t.topic}</strong><p>{new Date(t.due_at).toLocaleString()} · {t.format} · {t.state}</p>{t.error&&<small>{t.error}</small>}
      {t.job_id!==null&&<p>Job #{t.job_id} · {job?.state??'refreshing'} · {t.candidate_ids.length} suggested clips</p>}
      {!!t.candidate_ids.length&&<p>Candidate IDs: {t.candidate_ids.join(', ')}. Preview in Media Studio.</p>}
      <div className="inline-form">
      {t.state==='pending'&&<button type="button" className="button outline" disabled={busy} onClick={()=>change(t,'cancel')}>Cancel</button>}
      {(t.state==='failed'||t.state==='interrupted')&&<button type="button" className="button outline" disabled={busy} onClick={()=>change(t,'retry')}>Retry</button>}
      {t.job_id!==null&&<button type="button" className="button outline" disabled={busy} onClick={()=>inspect(t.job_id!)}>Inspect script</button>}
      {job?.state==='ready_for_review'&&<button type="button" className="button outline" onClick={onReview}>Approval center</button>}
      {job?.state==='approved'&&!!t.candidate_ids.length&&<button type="button" className="button primary" disabled={busy} onClick={()=>change(t,'render')}>Queue suggested montage</button>}
      </div></div></div>;})}
    {content&&inspected!==null&&<div className="stack-form"><h3>{content.result.title}</h3><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{content.result.script}</pre><p>Evidence checklist: {content.result.research_needed.join('; ')}</p><DraftContentEditor key={content.draft_id} base={base+'/ai'} draftId={content.draft_id} initial={content.result} onSaved={()=>inspect(inspected)}/></div>}
    </section></div>;
}
