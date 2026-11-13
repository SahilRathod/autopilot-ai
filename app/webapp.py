"""Read-only local dashboard; mutations happen through CLI to preserve approvals."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from html import escape
from .store import jobs
from .strategy import config

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/':
            self.send_error(404);return
        settings=config()
        rows=''.join(f"<tr><td>{j['id']}</td><td>{escape(j['game'])}</td><td>{escape(j['title'])}</td><td>{escape(j['format'])}</td><td>{escape(j['state'])}</td></tr>" for j in jobs())
        page=f"""<!doctype html><html><head><meta charset="utf-8"><title>Gaming Autopilot AI</title>
<style>body{{background:#0c1220;color:#ecf3ff;font:16px system-ui;max-width:1100px;margin:50px auto;padding:20px}}.box{{border:1px solid #304055;background:#161f31;padding:24px;border-radius:16px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:14px;border-bottom:1px solid #304055}}small{{color:#9db0c6}}</style></head>
<body><h1>🎮 Gaming Autopilot AI</h1><p>Local-first agent control dashboard · no paid APIs · dry-run only</p>
<section class="box"><h2>{escape(settings['channel_name'])}</h2><p>Games: {escape(', '.join(settings['games']))}</p>
<p>Monthly API/media budget: ₹{settings['budget_inr']} · publishing mode: {escape(settings['publishing_mode'])}</p>
<h2>Production queue</h2><table><tr><th>ID</th><th>Game</th><th>Title</th><th>Format</th><th>State</th></tr>{rows}</table>
<p><small>Use PowerShell CLI to add, render, review and approve. This starter does NOT publish to YouTube.</small></p></section></body></html>"""
        raw=page.encode('utf8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def serve():
    print('Open http://127.0.0.1:8765')
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
