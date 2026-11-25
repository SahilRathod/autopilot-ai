'use client';
import {FormEvent,useState} from 'react';
import {api} from '../lib/api';
type Fields={title:string;hook:string;script:string;description:string};
export default function DraftContentEditor({base,draftId,initial,onSaved}:{
  base:string;draftId:number;initial:Fields;onSaved:()=>void;
}){
  const [fields,setFields]=useState<Fields>({title:initial.title,hook:initial.hook,script:initial.script,description:initial.description});
  const [open,setOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');
  async function save(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError('');setNotice('');
    try{
      await api(base+'/drafts/'+draftId,{method:'PUT',body:JSON.stringify(fields)});
      setNotice('Reviewed text saved.');onSaved();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  return <div className="stack-form">
    <button type="button" className="button outline" onClick={()=>setOpen(v=>!v)}>{open?'Close editor':'Edit content before approval'}</button>
    {open&&<form className="stack-form" onSubmit={save}>
      <label>Title<input required maxLength={100} value={fields.title} onChange={e=>setFields(v=>({...v,title:e.target.value}))}/></label>
      <label>Hook<textarea required maxLength={1000} rows={2} value={fields.hook} onChange={e=>setFields(v=>({...v,hook:e.target.value}))}/></label>
      <label>Script<textarea required maxLength={12000} rows={8} value={fields.script} onChange={e=>setFields(v=>({...v,script:e.target.value}))}/></label>
      <label>Description<textarea required maxLength={5000} rows={4} value={fields.description} onChange={e=>setFields(v=>({...v,description:e.target.value}))}/></label>
      <button className="button primary" disabled={busy}>Save draft edits</button>
    </form>}
    {notice&&<div role="status" className="notice success">{notice}</div>}
    {error&&<div role="alert" className="notice danger">{error}</div>}
  </div>;
}
