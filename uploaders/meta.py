"""Instagram Reels and Facebook Page Reels through the Meta Graph API (Facebook Login).

One Page access token covers both: the Page itself and the Instagram account linked to it.
Videos are uploaded straight from disk (resumable upload), so no public hosting is needed.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import common
from .common import ApiError, request


def version() -> str:
    return os.environ.get("META_API_VERSION", "v25.0")


def graph() -> str:
    return f"https://graph.facebook.com/{version()}"


# ------------------------------------------------------------------ Instagram

def _wait_instagram(container: str, token: str, poll_s: int, max_wait: int) -> None:
    waited = 0
    while True:
        j = request("GET", f"{graph()}/{container}",
                    params={"fields": "status_code,status", "access_token": token}).json()
        code = j.get("status_code")
        if code in ("FINISHED", "PUBLISHED"):
            return
        if code in ("ERROR", "EXPIRED"):
            raise ApiError(f"Instagram could not process the video: {j.get('status') or code}")
        if waited >= max_wait:
            raise ApiError(f"Instagram still processing after {max_wait}s (container {container}); "
                           "nothing was published, safe to run again")
        common._sleep(poll_s)
        waited += poll_s


def instagram_reel(video_path, caption, *, ig_user_id, token, poll_s=30, max_wait=600):
    """Publish a Reel. Returns {"id": media_id, "url": permalink}."""
    data = Path(video_path).read_bytes()
    created = request("POST", f"{graph()}/{ig_user_id}/media",
                      data={"media_type": "REELS", "upload_type": "resumable",
                            "caption": caption, "access_token": token}).json()
    container = created["id"]
    upload_uri = created.get("uri") or \
        f"https://rupload.facebook.com/ig-api-upload/{version()}/{container}"

    up = request("POST", upload_uri, data=data,
                 headers={"Authorization": f"OAuth {token}", "offset": "0",
                          "file_size": str(len(data))}).json()
    if up.get("success") is False:
        raise ApiError(f"Instagram upload rejected: {up}")

    _wait_instagram(container, token, poll_s, max_wait)
    media_id = request("POST", f"{graph()}/{ig_user_id}/media_publish",
                       data={"creation_id": container, "access_token": token}).json()["id"]

    permalink = None
    try:
        permalink = request("GET", f"{graph()}/{media_id}",
                            params={"fields": "permalink", "access_token": token}
                            ).json().get("permalink")
    except ApiError:
        pass  # the Reel is live; the link is only for the log
    return {"id": media_id, "url": permalink}


def instagram_comment(media_id: str, message: str, *, token: str) -> str:
    return request("POST", f"{graph()}/{media_id}/comments",
                   data={"message": message, "access_token": token}).json()["id"]


# ------------------------------------------------------------------- Facebook

def _wait_facebook(video_id: str, token: str, poll_s: int, max_wait: int) -> str:
    """Poll until the Reel is live. Returns the last status seen (no error if still processing)."""
    waited = 0
    while True:
        status = request("GET", f"{graph()}/{video_id}",
                         params={"fields": "status", "access_token": token}
                         ).json().get("status", {})
        video_status = status.get("video_status", "unknown")
        publish_status = (status.get("publishing_phase") or {}).get("publish_status")
        if video_status == "ready" or publish_status == "published":
            return "published"
        if video_status in ("upload_failed", "expired", "error") or publish_status == "error":
            raise ApiError(f"Facebook rejected the Reel: video_status={video_status}, "
                           f"publish_status={publish_status}")
        if waited >= max_wait:
            return video_status
        common._sleep(poll_s)
        waited += poll_s


def facebook_reel(video_path, description, *, page_id, token, video_state="PUBLISHED",
                  poll_s=15, max_wait=600):
    """Publish a Reel to a Page. Returns {"id": video_id, "url": ..., "status": ...}."""
    data = Path(video_path).read_bytes()
    started = request("POST", f"{graph()}/{page_id}/video_reels",
                      data={"upload_phase": "start", "access_token": token}).json()
    video_id = started["video_id"]
    upload_url = started.get("upload_url") or \
        f"https://rupload.facebook.com/video-upload/{version()}/{video_id}"

    up = request("POST", upload_url, data=data,
                 headers={"Authorization": f"OAuth {token}", "offset": "0",
                          "file_size": str(len(data)),
                          "Content-Type": "application/octet-stream"}).json()
    if up.get("success") is False:
        raise ApiError(f"Facebook upload rejected: {up}")

    def finish(phase):
        return request("POST", f"{graph()}/{page_id}/video_reels",
                       data={"upload_phase": phase, "video_id": video_id,
                             "video_state": video_state, "description": description,
                             "access_token": token})

    try:
        finish("finish")
    except ApiError as exc:
        # Meta's docs use "finish" in the example but "complete" in the parameter table.
        if exc.status != 400:
            raise
        finish("complete")

    status = _wait_facebook(video_id, token, poll_s, max_wait)
    return {"id": video_id, "url": f"https://www.facebook.com/reel/{video_id}", "status": status}


def facebook_comment(video_id: str, message: str, *, token: str) -> str:
    return request("POST", f"{graph()}/{video_id}/comments",
                   data={"message": message, "access_token": token}).json()["id"]
