"""Read-only, on-demand YouTube Data API insights. No local analytics cache."""
from datetime import datetime, timezone
import re

from app import youtube_connection as yt

API = "https://www.googleapis.com/youtube/v3/"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")


def _access(w, c):
    link = yt._link(w, c)
    if not link:
        raise ValueError("Connect this channel first")
    client = yt.config()
    if client["client_id"] != link["client_id"]:
        raise ValueError("Use the original desktop OAuth client")
    return link["remote_channel_id"], yt.refresh_access(yt.unprotect(link["encrypted_refresh"]), client)


def _get(access, resource, params):
    return yt._json(yt._request("GET", API + resource,
        headers={"Authorization": "Bearer " + access}, params=params))


def _items(data):
    items = data.get("items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise RuntimeError("Invalid YouTube response")
    return items


def snapshot(w, c):
    remote, access = _access(w, c)
    items = _items(_get(access, "channels", {"part":"snippet,statistics,contentDetails","mine":"true","maxResults":50}))
    if len(items) != 1 or items[0].get("id") != remote:
        raise ValueError("Linked channel identity could not be verified")
    owner = items[0]
    stats = owner.get("statistics", {})
    playlist = owner.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not playlist:
        raise RuntimeError("YouTube did not return the channel uploads playlist")
    listing = _get(access, "playlistItems", {"part":"contentDetails","playlistId":playlist,"maxResults":50})
    ids = list(dict.fromkeys(item.get("contentDetails", {}).get("videoId") for item in _items(listing)))
    ids = [v for v in ids if isinstance(v,str) and VIDEO_ID.fullmatch(v)][:50]
    videos = []
    if ids:
        data = _get(access, "videos", {"part":"snippet,statistics,status,contentDetails","id":",".join(ids)})
        for item in _items(data):
            snippet = item.get("snippet", {})
            if item.get("id") not in ids or snippet.get("channelId") != remote:
                continue
            s = item.get("statistics", {})
            videos.append({"id":item["id"],"title":snippet.get("title","Untitled"),
                "published_at":snippet.get("publishedAt"),"privacy":item.get("status",{}).get("privacyStatus"),
                "views":s.get("viewCount"),"likes":s.get("likeCount"),"comments":s.get("commentCount"),
                "duration":item.get("contentDetails",{}).get("duration")})
        videos.sort(key=lambda v:ids.index(v["id"]))
    return {"fetched_at":datetime.now(timezone.utc).isoformat(),
            "channel":{"id":remote,"title":owner.get("snippet",{}).get("title",""),
                "subscribers":None if stats.get("hiddenSubscriberCount") else stats.get("subscriberCount"),
                "views":stats.get("viewCount"),"public_videos":stats.get("videoCount")},
            "videos":videos,"more_uploads":bool(listing.get("nextPageToken"))}


def comments(w, c, video):
    if not isinstance(video,str) or not VIDEO_ID.fullmatch(video):
        raise ValueError("Invalid video identifier")
    remote, access = _access(w,c)
    items = _items(_get(access,"videos",{"part":"snippet","id":video}))
    if len(items)!=1 or items[0].get("id")!=video or items[0].get("snippet",{}).get("channelId")!=remote:
        raise ValueError("Video not found on this linked channel")
    data = _get(access,"commentThreads",{"part":"snippet","videoId":video,"maxResults":50,
                                        "textFormat":"plainText","order":"time"})
    result = []
    for item in _items(data):
        thread = item.get("snippet", {})
        comment = thread.get("topLevelComment", {})
        info = comment.get("snippet", {})
        if comment.get("id"):
            result.append({"id":comment["id"],"text":info.get("textOriginal",info.get("textDisplay","")),
                           "author":info.get("authorDisplayName",""),"likes":info.get("likeCount"),
                           "published_at":info.get("publishedAt"),"replies":thread.get("totalReplyCount")})
    return result
