#!/usr/bin/env python3
"""Publish a day's brain-teaser Reel to Instagram, Facebook and YouTube, then post the answer.

    python3 publish_daily.py                       # today, every configured platform
    python3 publish_daily.py --dry-run             # show the plan, touch nothing
    python3 publish_daily.py --platforms yt        # one platform (ig, fb, yt; comma separated)
    python3 publish_daily.py --no-comment          # publish now, answer later ...
    python3 publish_daily.py --answers-only        # ... post the answer comments (run hours later)

Safe to re-run: what is already published is remembered in out/<date>/posted.json and skipped,
so a partial failure never causes a double post.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from uploaders import common, meta, youtube

HERE = Path(__file__).resolve().parent
LABELS = {"ig": "Instagram", "fb": "Facebook", "yt": "YouTube"}
REQUIRED = {
    "ig": ["META_PAGE_TOKEN", "IG_USER_ID"],
    "fb": ["META_PAGE_TOKEN", "META_PAGE_ID"],
    "yt": ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
}


def log(platform: str, message: str) -> None:
    print(f"[{platform}] {message}", flush=True)


def is_configured(p: str) -> bool:
    return all(os.environ.get(k, "").strip() for k in REQUIRED[p])


@dataclass
class Post:
    video: Path
    caption: str
    yt_title: str
    yt_description: str
    yt_tags: list
    yt_privacy: str
    fb_state: str


def _yt_creds() -> dict:
    return {"client_id": common.need("YOUTUBE_CLIENT_ID"),
            "client_secret": common.need("YOUTUBE_CLIENT_SECRET"),
            "refresh_token": common.need("YOUTUBE_REFRESH_TOKEN")}


def publish(p: str, post: Post) -> dict:
    if p == "ig":
        return meta.instagram_reel(post.video, post.caption, ig_user_id=common.need("IG_USER_ID"),
                                   token=common.need("META_PAGE_TOKEN"))
    if p == "fb":
        return meta.facebook_reel(post.video, post.caption, page_id=common.need("META_PAGE_ID"),
                                  token=common.need("META_PAGE_TOKEN"), video_state=post.fb_state)
    return youtube.youtube_short(post.video, post.yt_title, post.yt_description, post.yt_tags,
                                 privacy=post.yt_privacy, **_yt_creds())


def comment(p: str, post_id: str, text: str) -> str:
    if p == "ig":
        return meta.instagram_comment(post_id, text, token=common.need("META_PAGE_TOKEN"))
    if p == "fb":
        return meta.facebook_comment(post_id, text, token=common.need("META_PAGE_TOKEN"))
    return youtube.youtube_comment(post_id, text, **_yt_creds())


def ensure_video(folder: Path, d: date, args) -> None:
    if (folder / "video.mp4").exists() and (folder / "meta.json").exists():
        return
    cmd = [sys.executable, str(HERE / "make_daily.py"), "--date", d.isoformat(),
           "--out", str(args.out)]
    if args.handle:
        cmd += ["--handle", args.handle]
    print(f"Making {d.isoformat()}'s video first...", flush=True)
    subprocess.run(cmd, check=True, cwd=HERE)


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--date", help="ISO date, default today")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--state-dir", help="keep the posted-record here (<date>.json) instead of next to "
                                        "the video; used on GitHub Actions so it survives between runs")
    ap.add_argument("--platforms", help="ig,fb,yt - default: every platform that is configured")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, make no API calls")
    ap.add_argument("--no-comment", action="store_true", help="publish without the answer comment")
    ap.add_argument("--answers-only", action="store_true",
                    help="only post answer comments for posts already published")
    ap.add_argument("--handle", default="", help="page name shown in the video if it must be made")
    ap.add_argument("--yt-privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--fb-state", default="PUBLISHED", choices=["PUBLISHED", "DRAFT"],
                    help="DRAFT saves the Facebook Reel without publishing it (for testing)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    common.load_env()
    d = date.fromisoformat(args.date) if args.date else date.today()
    folder = Path(args.out) / d.isoformat()
    ensure_video(folder, d, args)

    info = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    caption = (folder / "caption.txt").read_text(encoding="utf-8")
    answer = (folder / "answer_comment.txt").read_text(encoding="utf-8")
    if args.state_dir:
        Path(args.state_dir).mkdir(parents=True, exist_ok=True)
        posted_path = Path(args.state_dir) / f"{d.isoformat()}.json"
    else:
        posted_path = folder / "posted.json"
    posted = json.loads(posted_path.read_text(encoding="utf-8")) if posted_path.exists() else {}

    # which platforms
    if args.platforms:
        chosen = [x.strip().lower() for x in args.platforms.split(",") if x.strip()]
        unknown = [x for x in chosen if x not in LABELS]
        if unknown:
            print(f"Unknown platform(s): {', '.join(unknown)} (use ig, fb, yt)")
            return 2
    else:
        chosen = [p for p in LABELS if is_configured(p)]
        if not chosen and args.dry_run:
            chosen = list(LABELS)
        if not chosen:
            print("No platform is configured yet - see SETUP.md")
            return 2

    post = Post(
        video=folder / "video.mp4", caption=caption,
        yt_title=f"Brain Teaser #{info['episode']}: {info['title']} #Shorts",
        yt_description=caption + "\n\n#Shorts",
        yt_tags=["brain teaser", "puzzle", "maths", "riddles", "iq test", "shorts"],
        yt_privacy=args.yt_privacy, fb_state=args.fb_state)

    def save():
        posted_path.write_text(json.dumps(posted, indent=2), encoding="utf-8")

    failures = []

    if not args.answers_only:
        for p in chosen:
            if posted.get(p, {}).get("id"):
                log(p, f"already published ({posted[p].get('url') or posted[p]['id']}) - skipping")
                continue
            if args.dry_run:
                note = "" if is_configured(p) else "  (NOT configured yet)"
                log(p, f"would upload {post.video.name} ({post.video.stat().st_size // 1024} KB){note}")
                continue
            try:
                log(p, "uploading...")
                result = publish(p, post)
                posted[p] = {**result, "published_at": datetime.now(timezone.utc).isoformat(),
                             "answer_comment_id": None}
                save()
                log(p, f"published: {result.get('url') or result['id']}")
                if result.get("privacy") == "private" and args.yt_privacy != "private":
                    log(p, "WARNING: YouTube made this video PRIVATE although you asked for "
                           f"{args.yt_privacy}. The Google project probably has not passed "
                           "YouTube's API audit - see SETUP.md.")
                if result.get("status") not in (None, "published"):
                    log(p, f"note: Facebook is still processing it (status: {result['status']})")
            except Exception as exc:  # keep going: one platform failing must not block the others
                failures.append((p, exc))
                log(p, f"FAILED: {exc}")

    if not args.no_comment:
        for p in chosen:
            entry = posted.get(p)
            if args.dry_run:
                log(p, f"would comment: {answer.splitlines()[0]}")
                continue
            if not entry or entry.get("answer_comment_id"):
                continue
            try:
                entry["answer_comment_id"] = comment(p, entry["id"], answer)
                save()
                log(p, "answer comment posted")
            except Exception as exc:
                failures.append((p, exc))
                log(p, f"answer comment FAILED (retry with --answers-only): {exc}")

    if failures:
        print(f"\n{len(failures)} problem(s): " + ", ".join(LABELS[p] for p, _ in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
