"""YouTube Shorts through the YouTube Data API v3 (plain REST, only needs `requests`).

There is no separate Shorts endpoint: a vertical video up to 3 minutes is a Short automatically.
"""
from __future__ import annotations

import json
from pathlib import Path

from .common import ApiError, request

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
COMMENT_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload "
          "https://www.googleapis.com/auth/youtube.force-ssl")


def access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    return request("POST", TOKEN_URL, data={
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"}).json()["access_token"]


def youtube_short(video_path, title, description, tags, *, client_id, client_secret,
                  refresh_token, privacy="public"):
    """Upload a Short. Returns {"id", "url", "privacy"}.

    `privacy` in the result is what YouTube actually applied - it can be "private" even when
    "public" was requested if the Google project has not passed YouTube's API audit.
    """
    token = access_token(client_id, client_secret, refresh_token)
    data = Path(video_path).read_bytes()
    metadata = {
        "snippet": {"title": title[:100], "description": description, "tags": tags,
                    "categoryId": "27"},  # 27 = Education
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    init = request("POST", UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                   headers={"Authorization": f"Bearer {token}",
                            "Content-Type": "application/json; charset=UTF-8",
                            "X-Upload-Content-Length": str(len(data)),
                            "X-Upload-Content-Type": "video/mp4"},
                   data=json.dumps(metadata))
    session_url = init.headers.get("Location")
    if not session_url:
        raise ApiError("YouTube did not return an upload session URL")

    done = request("PUT", session_url, data=data,
                   headers={"Content-Length": str(len(data)), "Content-Type": "video/mp4"}).json()
    video_id = done["id"]
    applied = (done.get("status") or {}).get("privacyStatus", privacy)
    return {"id": video_id, "url": f"https://www.youtube.com/shorts/{video_id}", "privacy": applied}


def youtube_comment(video_id: str, message: str, *, client_id, client_secret, refresh_token) -> str:
    """Post a top-level comment. (The API cannot pin it - pin it by hand in YouTube Studio.)"""
    token = access_token(client_id, client_secret, refresh_token)
    return request("POST", COMMENT_URL, params={"part": "snippet"},
                   headers={"Authorization": f"Bearer {token}"},
                   json={"snippet": {"videoId": video_id,
                                     "topLevelComment": {"snippet": {"textOriginal": message}}}}
                   ).json()["id"]
