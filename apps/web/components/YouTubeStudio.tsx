'use client';

import {useEffect, useState} from 'react';
import {api, type Channel} from '../lib/api';
import PrivateUploadPanel from './PrivateUploadPanel';
import ChannelInsights from './ChannelInsights';
import PublicationPanel from './PublicationPanel';

type Profile = {id:string; title:string; subscriber_count:string|null; video_count:string|null; view_count:string|null};
type Status = {configured:boolean; windows_supported:boolean; connected:boolean;
  upload_authorized:boolean; analytics_authorized:boolean; manage_authorized:boolean; permission:string; channel:Profile|null; updated_at:string|null};
type Auth = {authorization_url:string; expires_in:number};

export default function YouTubeStudio({workspaceId, channels, onChanged}: {
  workspaceId:number; channels:Channel[]; onChanged:()=>void;
}) {
  const [selected,setSelected]=useState<number|null>(channels[0]?.id ?? null);
  const current=channels.some(c=>c.id===selected)?selected:channels[0]?.id ?? null;
  const base=current===null?'':'/workspaces/'+workspaceId+'/channels/'+current+'/youtube';
  const [status,setStatus]=useState<Status|null>(null);
  const [auth,setAuth]=useState<Auth|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [confirm,setConfirm]=useState(false);
  const [reload,setReload]=useState(0);

  useEffect(()=>{
    let active=true;
    setStatus(null);setAuth(null);setError('');setConfirm(false);
    if(base)api<Status>(base).then(data=>{if(active)setStatus(data);})
      .catch(e=>{if(active)setError(String(e.message||e));});
    return()=>{active=false;};
  },[base,reload]);

  async function action(kind:'connect'|'authorize-upload'|'authorize-analytics'|'authorize-management'|'refresh'|'disconnect'|'forget'){
    if(!base||busy)return;
    setBusy(true);setError('');
    try{
      if(kind==='connect'||kind==='authorize-upload'||kind==='authorize-analytics'||kind==='authorize-management'){
        const result=await api<Auth>(base+'/'+kind,{method:'POST',body:'{}'});
        setAuth(result);
      }else{
        const result=await api<Status>(base+'/'+kind,{method:'POST',body:'{}'});
        setStatus(result);setAuth(null);setConfirm(false);onChanged();
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  return <section className="panel stack-form">
    <div className="panel-heading"><div><h2>Connect your YouTube channel</h2>
      <p>Official Google OAuth. Read-only by default; private uploads require separate authorization. Public scheduling and individual replies require separate management authorization and exact approval.</p>
    </div><span className="chip">YouTube Data API</span></div>
    {!channels.length?<p>Create a local channel profile in Channels first.</p>:<>
      <label>Local channel profile<select value={current??''} disabled={busy}
        onChange={e=>setSelected(Number(e.target.value))}>
        {channels.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
      </select></label>
      {error&&<div className="notice danger" role="alert">{error}</div>}
      {!status&&!error&&<p>Loading connection status…</p>}
      {status&&!status.windows_supported&&<p className="tip">Secure credential storage is currently supported on Windows only.</p>}
      {status&&!status.configured&&<div className="tip"><strong>Google setup required.</strong><p>Enable YouTube Data API v3 and create a Desktop OAuth client in Google Cloud. Save its downloaded JSON as data/youtube-client.json. Never paste credentials into chat.</p><a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">Open Google Cloud Console</a></div>}
      {status&&!status.connected&&<>
        <button type="button" className="button primary" disabled={busy||!status.configured||!status.windows_supported}
          onClick={()=>action('connect')}>Connect YouTube (read-only)</button>
        {auth&&<div className="tip"><p>Open Google authorization, select the correct YouTube channel and grant read-only permission. The link expires in ten minutes.</p>
          <a href={auth.authorization_url} target="_blank" rel="noreferrer">Continue to Google authorization</a>
          <p>After Google confirms the connection, return here and check the connection.</p></div>}
        <button type="button" className="button outline" disabled={busy} onClick={()=>{setReload(n=>n+1);onChanged();}}>Check connection</button>
      </>}
      {status?.connected&&status.channel&&<>
        <div className="channel-card"><div className="channel-avatar">YT</div><div>
          <h3>{status.channel.title}</h3><p>{status.channel.id}</p>
          <small>{status.permission} authorization · last updated {status.updated_at??'unknown'} UTC</small>
        </div></div>
        <div className="two-col">
          <div><strong>{status.channel.subscriber_count??'Unavailable'}</strong><p>Subscribers (as reported by YouTube)</p></div>
          <div><strong>{status.channel.video_count??'Unavailable'}</strong><p>Public videos</p></div>
          <div><strong>{status.channel.view_count??'Unavailable'}</strong><p>Channel views</p></div>
        </div>
        <button type="button" className="button outline" disabled={busy||!status.configured} onClick={()=>action('refresh')}>Refresh channel statistics</button>
        {!status.upload_authorized&&<>
          <button type="button" className="button primary" disabled={busy||!status.configured||!status.windows_supported}
            onClick={()=>action('authorize-upload')}>Authorize private uploads</button>
        </>}
        {!status.analytics_authorized&&<button type="button" className="button outline" disabled={busy||!status.configured||!status.windows_supported} onClick={()=>action('authorize-analytics')}>Authorize read-only analytics</button>}
        {!status.manage_authorized&&<><p>Management authorization is optional. Google grants broad rights to edit or delete videos and comments; this app uses it only for creator-approved schedules and individual replies.</p><button type="button" className="button outline" disabled={busy||!status.configured||!status.windows_supported} onClick={()=>action('authorize-management')}>Authorize publication and comment management</button></>}
        {auth&&<div className="tip"><p>Select the same linked channel and review the requested permissions.</p><a href={auth.authorization_url} target="_blank" rel="noreferrer">Continue to Google authorization</a></div>}
        <button type="button" className="button outline" disabled={busy} onClick={()=>{setReload(n=>n+1);onChanged();}}>Check authorization</button>
        <ChannelInsights key={base} base={base} authorized={status.analytics_authorized} management={status.manage_authorized}/>
        {status.manage_authorized&&<PublicationPanel key={base} base={base} remoteTitle={status.channel.title}/>}
        {status.upload_authorized&&current!==null&&<PrivateUploadPanel key={base} workspaceId={workspaceId} channelId={current} remoteTitle={status.channel.title} remoteId={status.channel.id}/>}
        <label><input type="checkbox" checked={confirm} disabled={busy} onChange={e=>setConfirm(e.target.checked)}/> I understand revocation may affect other grants for the same account; forgetting locally does not revoke Google access.</label>
        <button type="button" className="button outline" disabled={busy||!confirm} onClick={()=>action('disconnect')}>Disconnect and revoke</button>
        <button type="button" className="button outline" disabled={busy||!confirm} onClick={()=>action('forget')}>Forget local connection only</button>
        <p className="media-muted">If revocation fails, forget the local connection and remove access in <a href="https://myaccount.google.com/connections" target="_blank" rel="noreferrer">your Google account</a>.</p>
      </>}
    </>}
  </section>;
}
