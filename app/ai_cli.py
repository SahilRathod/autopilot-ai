"""No-npm local AI Director CLI for V0.4."""
import argparse
import asyncio
import json
from app import platform_core as core, ai_director as ai

def main():
    p=argparse.ArgumentParser(description="Autopilot AI Director v0.4")
    s=p.add_subparsers(dest="action",required=True)
    for action in ("generate","remember","drafts","submit"):
        cmd=s.add_parser(action)
        cmd.add_argument("--workspace",type=int,required=True)
        cmd.add_argument("--channel",type=int,required=True)
        if action=="generate":
            cmd.add_argument("--topic",required=True)
            cmd.add_argument("--format",choices=("short","long"),default="short")
        if action=="remember":
            cmd.add_argument("--key",required=True)
            cmd.add_argument("--value",required=True)
        if action=="submit":
            cmd.add_argument("--draft",type=int,required=True)
    a=p.parse_args()
    core.initialize()
    ai.initialize()
    try:
        if a.action=="generate":
            result=asyncio.run(ai.generate(a.workspace,a.channel,a.topic,a.format))
        elif a.action=="remember":
            ai.remember(a.workspace,a.channel,a.key,a.value)
            result={"saved":True}
        elif a.action=="drafts":
            result=ai.drafts(a.workspace,a.channel)
        else:
            result={"job_id":ai.submit(a.workspace,a.channel,a.draft),"published":False}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,ai.AIError) as exc:
        p.error(str(exc))

if __name__=="__main__":
    main()
