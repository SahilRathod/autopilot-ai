"""Run against an isolated temporary DB and production Next build; no Google traffic."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
API_PORT = 18000
WEB_PORT = 13000
WEB = f"http://127.0.0.1:{WEB_PORT}"


def wait_url(url, process):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("Application process exited early")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(.5)
    raise RuntimeError("Application did not become healthy")


def main():
    with tempfile.TemporaryDirectory(prefix="autopilot-browser-") as temp:
        folder = Path(temp)
        env = os.environ | {"AUTOPILOT_API_PORT": str(API_PORT),
                            "AUTOPILOT_BROWSER_TEMP": str(folder)}
        setup = """
import os
from pathlib import Path
from app import platform_core, editor
root = Path(os.environ['AUTOPILOT_BROWSER_TEMP'])
platform_core.DB = root / 'platform.sqlite3'
editor.RAW = root / 'raw'
editor.OUT = root / 'output'
editor.RAW.mkdir()
editor.OUT.mkdir()
import uvicorn
uvicorn.run('apps.api.main:app', host='127.0.0.1', port=18000, access_log=False)
"""
        processes = []
        with (folder/"api.log").open("w+") as api_log, (folder/"web.log").open("w+") as web_log:
            try:
                backend = subprocess.Popen([sys.executable,"-c",setup],cwd=ROOT,env=env,
                                           stdout=api_log,stderr=subprocess.STDOUT)
                processes.append(backend)
                wait_url(f"http://127.0.0.1:{API_PORT}/api/v1/health",backend)
                web = subprocess.Popen(["node","node_modules/next/dist/bin/next","start",
                                        "--port",str(WEB_PORT),"--hostname","127.0.0.1"],
                                       cwd=ROOT/"apps/web",env=env,stdout=web_log,stderr=subprocess.STDOUT)
                processes.append(web)
                wait_url(WEB,web)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page()
                    page.set_default_timeout(15000)
                    page.route("**/*",lambda route:route.continue_() if urlsplit(route.request.url).hostname in ("127.0.0.1","localhost") else route.abort())
                    page.goto(WEB)
                    page.get_by_placeholder("e.g. My Creator Studio").fill("Browser smoke workspace")
                    page.get_by_role("button",name="Create workspace",exact=True).click()
                    expect(page.get_by_role("heading",name="Welcome to Browser smoke workspace")).to_be_visible()
                    page.locator("nav button").filter(has_text="Channels").click()
                    page.get_by_placeholder("e.g. Gaming Universe").fill("Browser smoke gaming")
                    page.get_by_role("button",name="+ Add channel",exact=True).click()
                    expect(page.get_by_role("heading",name="Browser smoke gaming")).to_be_visible()
                    page.locator("nav button").filter(has_text="Production queue").click()
                    page.get_by_placeholder("e.g. Valorant Beginner Tips").fill("Browser smoke draft")
                    page.get_by_role("button",name="+ Create draft",exact=True).click()
                    expect(page.get_by_role("heading",name="Browser smoke draft")).to_be_visible()
                    page.get_by_role("button",name="Submit for review",exact=True).click()
                    page.locator("nav button").filter(has_text="Approval center").click()
                    expect(page.get_by_role("heading",name="Browser smoke draft")).to_be_visible()
                    page.get_by_role("button",name="Approve",exact=True).click()
                    page.locator("nav button").filter(has_text="Production queue").click()
                    expect(page.get_by_text("approved",exact=True)).to_be_visible()
                    page.locator("nav button").filter(has_text="YouTube accounts").click()
                    expect(page.get_by_role("heading",name="Connect your YouTube channel")).to_be_visible()
                    expect(page.get_by_role("button",name="Connect YouTube (read-only)")).to_be_disabled()
                    page.reload()
                    page.locator("nav button").filter(has_text="Production queue").click()
                    expect(page.get_by_role("heading",name="Browser smoke draft")).to_be_visible()
                    expect(page.get_by_text("approved",exact=True)).to_be_visible()
                    browser.close()
                with urlopen(WEB+"/api/v1/health",timeout=5) as response:
                    assert json.load(response)["mode"] == "local"
                print("PASS: real Chromium + Next + FastAPI workspace, channel, draft, approval, reload and safe disconnected YouTube")
            except Exception:
                for log in (api_log,web_log):
                    log.flush();log.seek(0)
                    print(log.read(),file=sys.stderr)
                raise
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__=="__main__":
    main()
