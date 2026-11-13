import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'channel.json'


def config(): return json.loads(CONFIG.read_text(encoding='utf8'))


def proposals():
    games=config()['games']
    patterns=[
      ('short','{game} Mein Ye Beginner Mistake Mat Karna!'),
      ('short','{game} Ka Sabse Useful Quick Tip'),
      ('long','{game}: 7 Mistakes Aur Unke Real Fixes'),
      ('short','{game} Challenge: One Unexpected Moment'),
    ]
    return [{'game':games[i%len(games)],'format':fmt,'title':title.format(game=games[i%len(games)])} for i,(fmt,title) in enumerate(patterns)]


def script_brief(job):
    return (f"LANGUAGE: Roman-script Hinglish.\nGAME: {job['game']}\n"
            f"FORMAT: {job['format']}\nTITLE: {job['title']}\n"
            "Write a concise, entertaining script. Use ONLY footage documented by the creator. "
            "Hook -> genuine gameplay example -> practical explanation -> short CTA. "
            "Mark missing footage as REQUIRED. No invented claims or fake results.")
