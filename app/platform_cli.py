"""Independent CLI for the multi-channel foundation."""
import argparse
import json
from . import platform_core as core, media_pipeline, media_intelligence

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
