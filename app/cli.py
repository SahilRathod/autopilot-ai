import argparse
import json
from pathlib import Path
from . import store, strategy, editor


def main():
    p=argparse.ArgumentParser(description='Gaming Autopilot AI — free local-first MVP')
    commands=p.add_subparsers(dest='command',required=True)
    commands.add_parser('init');commands.add_parser('plan');commands.add_parser('list')
    add=commands.add_parser('add');add.add_argument('--game',required=True);add.add_argument('--title',required=True)
    add.add_argument('--format',choices=['short','long'],required=True)
    add.add_argument('--source',help='A video filename inside media/raw/')
    brief=commands.add_parser('brief');brief.add_argument('id',type=int)
    render=commands.add_parser('render');render.add_argument('id',type=int)
    render.add_argument('--start',type=float,default=0);render.add_argument('--seconds',type=float,default=30)
    approve=commands.add_parser('approve');approve.add_argument('id',type=int)
    reject=commands.add_parser('reject');reject.add_argument('id',type=int)
    schedule=commands.add_parser('schedule');schedule.add_argument('id',type=int)
    commands.add_parser('serve')
    args=p.parse_args();store.initialize()
    try:
        if args.command=='init': print('Database ready. Run python -m app.cli plan')
        elif args.command=='plan': print(json.dumps(strategy.proposals(),indent=2))
        elif args.command=='list': print(json.dumps(store.jobs(),indent=2))
        elif args.command=='add':
            if args.source: editor.source(args.source)
            print('Created draft job',store.create(args.game,args.title,args.format,args.source))
        elif args.command=='brief': print(strategy.script_brief(store.get(args.id)))
        elif args.command=='render':
            job=store.get(args.id)
            if job['state']!='draft':raise ValueError('Only draft jobs can render')
            if not job['source_path']:raise ValueError('Add a job with --source first')
            output=editor.highlight(job['source_path'],args.start,args.seconds,job['format']=='short',f'job_{args.id}.mp4')
            store.update_state(args.id,'rendered',output);print('Rendered:',output)
        elif args.command in ('approve','reject','schedule'):
            target={'approve':'approved','reject':'rejected','schedule':'scheduled'}[args.command]
            store.update_state(args.id,target)
            print('Job status:',target, '(scheduling is a local marker: no YouTube upload occurs)')
        elif args.command=='serve':
            from .webapp import serve;serve()
    except (ValueError,RuntimeError) as exc:
        p.error(str(exc))

if __name__=='__main__':main()
