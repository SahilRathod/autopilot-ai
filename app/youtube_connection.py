"""Local Windows YouTube OAuth. No API keys, passwords or tokens returned to UI."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx

from app import platform_core as core, media_intelligence as media

READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"
_pending = {}
_lock = threading.RLock()


def initialize():
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS youtube_links (
            local_channel_id INTEGER PRIMARY KEY REFERENCES channels(id),
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            remote_channel_id TEXT NOT NULL UNIQUE,
            profile_json TEXT NOT NULL,
            encrypted_refresh BLOB NOT NULL,
            client_id TEXT NOT NULL,
            connected_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            upload_authorized INTEGER NOT NULL DEFAULT 0,
            analytics_authorized INTEGER NOT NULL DEFAULT 0
        )""")
        if "upload_authorized" not in {r["name"] for r in db.execute("PRAGMA table_info(youtube_links)")}:
            db.execute("ALTER TABLE youtube_links ADD COLUMN upload_authorized INTEGER NOT NULL DEFAULT 0")
        if "analytics_authorized" not in {r["name"] for r in db.execute("PRAGMA table_info(youtube_links)")}:
            db.execute("ALTER TABLE youtube_links ADD COLUMN analytics_authorized INTEGER NOT NULL DEFAULT 0")


def _dpapi(value, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("YouTube connection requires Windows user credential protection")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source = Blob(len(value), buffer)
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("Windows could not protect or unlock the YouTube credential")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def protect(value):
    return _dpapi(value.encode("utf-8"))


def unprotect(value):
    return _dpapi(value, decrypt=True).decode("utf-8")


def config():
    path = core.DB.parent / "youtube-client.json"
    try:
        if path.stat().st_size > 65536:
            raise ValueError("OAuth client file too large")
        client = json.loads(path.read_text(encoding="utf-8-sig"))["installed"]
        client_id, secret = client["client_id"], client["client_secret"]
        if not isinstance(client_id, str) or not client_id.endswith(".apps.googleusercontent.com"):
            raise ValueError("Use a Google desktop OAuth client")
        if not isinstance(secret, str) or not secret:
            raise ValueError("Missing desktop client secret")
        return {"client_id": client_id, "client_secret": secret}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Save a valid Google Desktop OAuth client JSON as data/youtube-client.json") from exc


def redirect_uri():
    try:
        port = int(os.environ.get("AUTOPILOT_API_PORT", "8000"))
    except ValueError as exc:
        raise ValueError("Invalid AUTOPILOT_API_PORT") from exc
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid AUTOPILOT_API_PORT")
    return f"http://127.0.0.1:{port}/api/v1/youtube/callback"


def _link(w, c):
    media._channel(w, c)
    initialize()
    with core.connect() as db:
        return db.execute("SELECT * FROM youtube_links WHERE workspace_id=? AND local_channel_id=?",
                          (w, c)).fetchone()


def status(w, c):
    row = _link(w, c)
    try:
        config()
        configured = True
    except ValueError:
        configured = False
    return {"configured": configured, "windows_supported": os.name == "nt",
            "connected": row is not None,
            "upload_authorized": bool(row and row["upload_authorized"]),
            "analytics_authorized": bool(row and row["analytics_authorized"]),
            "permission": "read and private upload" if row and row["upload_authorized"] else "read-only",
            "channel": json.loads(row["profile_json"]) if row else None,
            "updated_at": row["updated_at"] if row else None}


def clear_pending():
    with _lock:
        _pending.clear()


def begin(w, c, upload=False, analytics=False):
    with _lock:
        old = _link(w, c)
        if old and not ((upload and not old["upload_authorized"]) or (analytics and not old["analytics_authorized"])):
            raise ValueError("Disconnect the existing channel before reconnecting")
        if analytics and not old:
            raise ValueError("Connect a channel before enabling analytics")
        upload = bool(upload or (old and old["upload_authorized"]))
        analytics = bool(analytics or (old and old["analytics_authorized"]))
        requested_scopes = [READ_SCOPE] + ([UPLOAD_SCOPE] if upload else []) + ([ANALYTICS_SCOPE] if analytics else [])
        client = config()
        protect("credential-storage-check")  # fail before asking for consent on unsupported systems
        now = time.monotonic()
        for state, record in list(_pending.items()):
            if record["expires"] <= now or (record["w"], record["c"]) == (w, c):
                _pending.pop(state)
        if len(_pending) >= 32:
            raise ValueError("Too many pending connections; try again later")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        uri = redirect_uri()
        _pending[state] = dict(w=w, c=c, expires=now + 600, verifier=verifier,
                               client_id=client["client_id"], redirect_uri=uri, upload=upload, analytics=analytics,
                               required_scopes=requested_scopes,
                               expected_remote=old["remote_channel_id"] if old else None)
        query = urlencode({"client_id": client["client_id"], "redirect_uri": uri,
            "response_type": "code", "scope": " ".join(requested_scopes), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
            "access_type": "offline", "prompt": "consent select_account"})
        return {"authorization_url": AUTH_URL + "?" + query, "expires_in": 600}


def _request(method, url, **kwargs):
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=5), follow_redirects=False) as client:
            response = client.request(method, url, **kwargs)
        if not response.is_success:
            raise RuntimeError(f"Google request failed (HTTP {response.status_code}); check authorization and API access")
        return response
    except httpx.HTTPError as exc:
        raise RuntimeError("Google could not be reached; check internet connectivity") from exc


def _json(response):
    try:
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except ValueError as exc:
        raise RuntimeError("Google returned an invalid response") from exc


def exchange_code(code, record, client):
    return _json(_request("POST", TOKEN_URL, data=client | {
        "code": code, "code_verifier": record["verifier"],
        "redirect_uri": record["redirect_uri"], "grant_type": "authorization_code"}))


def refresh_access(refresh, client):
    result = _json(_request("POST", TOKEN_URL, data=client | {
        "refresh_token": refresh, "grant_type": "refresh_token"}))
    token = result.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Google did not return an access token")
    return token


def read_channel(access):
    result = _json(_request("GET", CHANNEL_URL,
        headers={"Authorization": "Bearer " + access},
        params={"part": "snippet,statistics", "mine": "true", "maxResults": 50}))
    items = result.get("items", [])
    if len(items) != 1 or result.get("nextPageToken"):
        raise ValueError("Select a Google identity with exactly one authorized YouTube channel")
    item = items[0]
    snippet, stats = item.get("snippet", {}), item.get("statistics", {})
    if not item.get("id") or not snippet.get("title"):
        raise ValueError("No usable YouTube channel returned by Google")
    return {"id": item["id"], "title": snippet["title"],
            "subscriber_count": None if stats.get("hiddenSubscriberCount") else stats.get("subscriberCount"),
            "video_count": stats.get("videoCount"), "view_count": stats.get("viewCount"),
            "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url", "")}


def finish(state, code):
    with _lock:
        record = _pending.pop(state, None)
        if record is None or record["expires"] <= time.monotonic() or not code:
            raise ValueError("Authorization expired, denied, or already used; start a new connection")
        w, c = record["w"], record["c"]
        old = _link(w, c)
        if (old["remote_channel_id"] if old else None) != record["expected_remote"]:
            raise ValueError("Local connection changed; restart authorization")
        client = config()
        if client["client_id"] != record["client_id"]:
            raise ValueError("OAuth configuration changed; restart authorization")
        token = exchange_code(code, record, client)
        scopes = set(token.get("scope", "").split())
        if not set(record["required_scopes"]).issubset(scopes):
            raise ValueError("Required YouTube permissions were not granted")
        access, refresh = token.get("access_token"), token.get("refresh_token")
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
            raise ValueError("Google did not grant offline access; revoke the app in Google settings and reconnect")
        channel = read_channel(access)
        if old and channel["id"] != old["remote_channel_id"]:
            raise ValueError("Select the same YouTube channel when upgrading permissions")
        encrypted = protect(refresh)
        with core.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if old:
                changed = db.execute("""UPDATE youtube_links SET profile_json=?,encrypted_refresh=?,
                    client_id=?,upload_authorized=?,analytics_authorized=?,updated_at=CURRENT_TIMESTAMP
                    WHERE local_channel_id=? AND workspace_id=? AND remote_channel_id=? AND upload_authorized=? AND analytics_authorized=?""",
                    (json.dumps(channel),encrypted,client["client_id"],int(record["upload"]),int(record["analytics"]),c,w,channel["id"],old["upload_authorized"],old["analytics_authorized"])).rowcount
                if changed != 1:
                    raise ValueError("Local connection changed; restart authorization")
            else:
                if db.execute("SELECT 1 FROM youtube_links WHERE remote_channel_id=? OR local_channel_id=?",
                              (channel["id"], c)).fetchone():
                    raise ValueError("This YouTube channel is already linked to a local profile")
                db.execute("""INSERT INTO youtube_links
                    (local_channel_id,workspace_id,remote_channel_id,profile_json,encrypted_refresh,client_id,upload_authorized,analytics_authorized)
                    VALUES(?,?,?,?,?,?,?,?)""", (c, w, channel["id"], json.dumps(channel), encrypted,
                                               client["client_id"],int(record["upload"]),int(record["analytics"])))
            db.execute("INSERT INTO audit_log(workspace_id,channel_id,action) VALUES(?,?,'youtube_connected')", (w,c))
        return status(w, c)


def refresh(w, c):
    with _lock:
        row = _link(w, c)
        if not row:
            raise ValueError("Connect a YouTube channel first")
        client = config()
        if client["client_id"] != row["client_id"]:
            raise ValueError("Use the original desktop OAuth client")
        access = refresh_access(unprotect(row["encrypted_refresh"]), client)
        channel = read_channel(access)
        if channel["id"] != row["remote_channel_id"]:
            raise ValueError("YouTube channel identity changed; reconnect explicitly")
        with core.connect() as db:
            db.execute("""UPDATE youtube_links SET profile_json=?,updated_at=CURRENT_TIMESTAMP
                          WHERE local_channel_id=? AND workspace_id=?""", (json.dumps(channel),c,w))
        return status(w, c)


def revoke_token(token):
    _request("POST", REVOKE_URL, data={"token": token})


def disconnect(w, c):
    with _lock:
        row = _link(w, c)
        if not row:
            return status(w, c)
        revoke_token(unprotect(row["encrypted_refresh"]))
        with core.connect() as db:
            db.execute("DELETE FROM youtube_links WHERE local_channel_id=? AND workspace_id=?", (c,w))
            db.execute("INSERT INTO audit_log(workspace_id,channel_id,action) VALUES(?,?,'youtube_disconnected')",(w,c))
        return status(w,c)


def forget_local(w, c):
    """Remove local credentials after explicit action, even if Google is unreachable."""
    with _lock:
        _link(w, c)
        for state, record in list(_pending.items()):
            if (record["w"], record["c"]) == (w,c):
                _pending.pop(state)
        with core.connect() as db:
            db.execute("DELETE FROM youtube_links WHERE local_channel_id=? AND workspace_id=?", (c,w))
            db.execute("INSERT INTO audit_log(workspace_id,channel_id,action) VALUES(?,?,'youtube_forgot_local')",(w,c))
        return status(w,c)


def workspace_connected(w):
    initialize()
    with core.connect() as db:
        return db.execute("SELECT 1 FROM youtube_links WHERE workspace_id=? LIMIT 1", (w,)).fetchone() is not None
