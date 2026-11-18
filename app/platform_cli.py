"""Independent CLI for the multi-channel foundation."""
import argparse
import json
from . import platform_core as core, media_pipeline, media_intelligence, highlight_ranker, video_assembly

def main():
    p=argparse.ArgumentParser(description='Autopilot AI local multi-channel base')
    s=p.add_subparsers(dest='action',required=True)
    s.add_parser('init')
    w=s.add_parser('workspace-add');w.add_argument('name')
    ch=s.add_parser('channel-add');ch.add_argument('--workspace',type=int,required=True);ch.add_argument('--name',required=True);ch.add_argument('--niche',required=True);ch.add_argument('--language',default='Hinglish')
    ls=s.add_parser('channels');ls.add_argument('--workspace',type=int,required=True)
    add=s.add_parser('job-add');add.add_argument('--workspace',type=int,required=True);add.add_argument('--channel',type=int,required=True);add.add_argument('--title',required=True);add.add_argument('--format',choices=['short','long'],required=True)
    jobs=s.add_parser('jobs');jobs.add_argument('--workspace',type=int,required=True);jobs.add_argument('--channel',type=int)
    update=s.add_parser('transition');update.add_argument('--workspace',type=int,required=True);update.add_argument('--job',type=int,required=True);update.add_argument('--to',choices=list(core.STATES))
    render=s.add_parser('render-job')
    render.add_argument('--workspace',type=int,required=True)
    render.add_argument('--job',type=int,required=True)
    render.add_argument('--source',required=True,help='Video filename in media/raw/')
    render.add_argument('--start',type=float,default=0)
    render.add_argument('--seconds',type=float,default=30)
    media_add=s.add_parser('media-import')
    media_add.add_argument('--workspace',type=int,required=True)
    media_add.add_argument('--channel',type=int,required=True)
    media_add.add_argument('--source',required=True)
    media_list=s.add_parser('media-list')
    media_list.add_argument('--workspace',type=int,required=True)
    media_list.add_argument('--channel',type=int,required=True)
    scan=s.add_parser('media-scan')
    scan.add_argument('--workspace',type=int,required=True)
    scan.add_argument('--channel',type=int,required=True)
    scan.add_argument('--asset',type=int,required=True)
    scan.add_argument('--seconds',type=float,default=30)
    scan.add_argument('--threshold',type=float,default=0.35)
    scan.add_argument('--scan-seconds',type=float,default=120)
    suggestions=s.add_parser('media-candidates')
    suggestions.add_argument('--workspace',type=int,required=True)
    suggestions.add_argument('--channel',type=int,required=True)
    suggestions.add_argument('--asset',type=int,required=True)
    score=s.add_parser('media-rank')
    score.add_argument('--workspace',type=int,required=True)
    score.add_argument('--channel',type=int,required=True)
    score.add_argument('--asset',type=int,required=True)
    score.add_argument('--profile',choices=('balanced','tactical','sandbox'),default='balanced')
    score.add_argument('--scan-seconds',type=float,default=120)
    ranked=s.add_parser('media-rankings')
    ranked.add_argument('--workspace',type=int,required=True)
    ranked.add_argument('--channel',type=int,required=True)
    ranked.add_argument('--asset',type=int,required=True)
    ranked.add_argument('--profile',choices=('balanced','tactical','sandbox'),default='balanced')
    assembly=s.add_parser('media-assemble')
    assembly.add_argument('--workspace',type=int,required=True)
    assembly.add_argument('--channel',type=int,required=True)
    assembly.add_argument('--job',type=int,required=True)
    assembly.add_argument('--candidates',type=int,nargs='+',required=True)
    assembly.add_argument('--quality',choices=('fast','high'),default='fast')
    assembly.add_argument('--audio',choices=('preserve','normalize','mute'),default='preserve')
    assembly.add_argument('--captions',choices=('none','soft','burn'),default='none')
    assembly.add_argument('--caption-file',help='UTF-8 text file; one user-authored caption per line')
    exports=s.add_parser('media-exports')
    exports.add_argument('--workspace',type=int,required=True)
    exports.add_argument('--channel',type=int,required=True)
    chosen=s.add_parser('media-render')
    chosen.add_argument('--workspace',type=int,required=True)
    chosen.add_argument('--channel',type=int,required=True)
    chosen.add_argument('--candidate',type=int,required=True)
    chosen.add_argument('--job',type=int,required=True)
    log=s.add_parser('audit');log.add_argument('--workspace',type=int,required=True)
    args=p.parse_args()
    core.initialize()
    try:
        if args.action=='init': result='Platform database initialized'
        elif args.action=='workspace-add': result={'workspace_id':core.new_workspace(args.name)}
        elif args.action=='channel-add': result={'channel_id':core.new_channel(args.workspace,args.name,args.niche,args.language)}
        elif args.action=='channels': result=core.channels(args.workspace)
        elif args.action=='job-add': result={'job_id':core.add_job(args.workspace,args.channel,args.title,args.format)}
        elif args.action=='jobs': result=core.jobs(args.workspace,args.channel)
        elif args.action=='media-import':
            result=media_intelligence.import_media(args.workspace,args.channel,args.source)
        elif args.action=='media-list':
            result=media_intelligence.assets(args.workspace,args.channel)
        elif args.action=='media-scan':
            result=media_intelligence.scan_media(args.workspace,args.channel,args.asset,
                                                 args.seconds,args.threshold,args.scan_seconds)
        elif args.action=='media-candidates':
            result=media_intelligence.candidates(args.workspace,args.channel,args.asset)
        elif args.action=='media-rank':
            result=highlight_ranker.rank_asset(args.workspace,args.channel,args.asset,
                                                args.profile,args.scan_seconds)
        elif args.action=='media-rankings':
            result=highlight_ranker.rankings(args.workspace,args.channel,args.asset,
                                             args.profile)
        elif args.action=='media-assemble':
            from pathlib import Path
            caption_lines=[]
            if args.caption_file:
                pth=Path(args.caption_file)
                if pth.stat().st_size > 10000: raise ValueError('Caption text file too large')
                caption_lines=[line.strip() for line in pth.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
            result=video_assembly.export_job(args.workspace,args.channel,args.job,args.candidates,
                                             args.quality,args.audio,args.captions,caption_lines)
        elif args.action=='media-exports':
            result=video_assembly.exports(args.workspace,args.channel)
        elif args.action=='media-render':
            result=media_intelligence.render_candidate(args.workspace,args.channel,
                                                       args.candidate,args.job)
        elif args.action=='render-job':
            result=media_pipeline.render_job(args.workspace,args.job,args.source,args.start,args.seconds)
        elif args.action=='transition': core.transition(args.workspace,args.job,args.to);result={'status':args.to,'external_upload':False}
        else: result=core.audit(args.workspace)
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except ValueError as exc: p.error(str(exc))

if __name__=='__main__': main()
