'use client';

import {useEffect,useState} from 'react';
import {api} from '../lib/api';

type Revision={id:number;operation:string;caption_mode:string;active:boolean;created_at?:string};
export default function PostProductionPanel({base,jobId,duration,onChanged}:{
  base:string;jobId:number;duration:number;onChanged:()=>void;
}){
  const path=base+'/exports/'+jobId;
  const [srt,setSrt]=useState('');
  const [voice,setVoice]=useState('');
  const [game,setGame]=useState(0.25);
  const [narration,setNarration]=useState(1);
  const [timestamp,setTimestamp]=useState(0);
  const [thumb,setThumb]=useState('');
  const [revisions,setRevisions]=useState<Revision[]>([]);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;
    api<Revision[]>(path+'/revisions').then(data=>{if(active)setRevisions(data);})
      .catch(e=>{if(active)setError(e instanceof Error?e.message:String(e));});
    return()=>{active=false;};
  },[path]);

  async function run(action:string,data?:unknown){
    setBusy(true);setError('');setNotice('');
    try{
      await api(path+action,{method:'POST',body:JSON.stringify(data??{})});
      if(action==='/thumbnail'){
        setThumb('/api/v1'+path+'/thumbnail?v='+Date.now());
        setNotice('Thumbnail created locally.');
      }else{
        setRevisions(await api<Revision[]>(path+'/revisions'));
        onChanged();
        setNotice('Active export updated. Previous versions remain available.');
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }

  return <div className="assembly-results stack-form">
    <h3>Post-production tools</h3>
    <p>Finish the reviewed video before requesting a private upload. Earlier versions are preserved.</p>
    {error&&<div className="notice danger" role="alert">{error}</div>}
    {notice&&<div className="notice success" role="status">{notice}</div>}
    <h4>Timed captions (SRT)</h4>
    <label>Open a local SRT file<input type="file" accept=".srt,text/plain" disabled={busy}
      onChange={async e=>{const f=e.target.files?.[0];if(f){if(f.size>131072){setError('SRT exceeds 128 KiB');return;}setSrt(await f.text());}}}/></label>
    <label>Review and edit timestamps<textarea rows={7} value={srt} disabled={busy} maxLength={131072}
      placeholder={'1\n00:00:00,000 --> 00:00:02,000\nYour caption'} onChange={e=>setSrt(e.target.value)}/></label>
    <button type="button" className="button outline" disabled={busy||!srt.trim()} onClick={()=>run('/captions',{srt})}>Attach timed subtitle track</button>
    <p className="media-muted">For automatic transcription, install the optional local Whisper model and use the documented CLI. Check the transcript and upload captions separately in YouTube Studio if required.</p>
    <h4>Mix narration</h4>
    <label>Audio filename in media/raw/<input value={voice} disabled={busy} placeholder="narration.wav" onChange={e=>setVoice(e.target.value)}/></label>
    <label>Original video volume ({game.toFixed(2)})<input type="range" min={0} max={2} step={0.05} value={game} disabled={busy} onChange={e=>setGame(Number(e.target.value))}/></label>
    <label>Narration volume ({narration.toFixed(2)})<input type="range" min={0.05} max={2} step={0.05} value={narration} disabled={busy} onChange={e=>setNarration(Number(e.target.value))}/></label>
    <button type="button" className="button outline" disabled={busy||!voice.trim()} onClick={()=>run('/narration',{filename:voice.trim(),game_volume:game,voice_volume:narration})}>Mix narration into export</button>
    <h4>Thumbnail frame</h4>
    <label>Timestamp (seconds)<input type="number" min={0} max={Math.max(0,duration-0.1)} step={0.1} value={timestamp} disabled={busy} onChange={e=>setTimestamp(Number(e.target.value))}/></label>
    <button type="button" className="button outline" disabled={busy||timestamp<0||timestamp>=duration} onClick={()=>run('/thumbnail',{timestamp})}>Create 1280×720 thumbnail</button>
    {thumb&&<img src={thumb} alt="Generated local thumbnail" style={{maxWidth:'100%',borderRadius:8}}/>}
    <a href={'/api/v1'+path+'/thumbnail'} target="_blank" rel="noreferrer">Open saved thumbnail (after generation)</a>
    <h4>Video versions</h4>
    {revisions.map(r=><div className="assembly-clip-row" key={r.id}><div>
      <strong>{r.operation.replaceAll('_',' ')}</strong><p>{r.caption_mode} captions · {r.active?'Active export':'Previous version'}</p>
    </div>{!r.active&&r.id>0&&<button type="button" className="button outline" disabled={busy} onClick={()=>run('/revisions/'+r.id+'/activate')}>Use this version</button>}</div>)}
    <p className="media-muted">Editing is disabled after an upload record exists. Finishing operations run locally and may take time.</p>
  </div>;
}
