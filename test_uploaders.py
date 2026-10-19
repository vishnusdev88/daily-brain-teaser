"""Offline tests: every HTTP call is faked, so nothing is ever posted.

    python3 -m unittest test_uploaders -v
"""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import publish_daily
from uploaders import common

VIDEO = b"\x00fake-mp4-bytes" * 100
G = "https://graph.facebook.com/v25.0"


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeWeb:
    """Routes the calls our code makes to canned answers and records them."""

    def __init__(self):
        self.calls = []
        self.ig_polls = 0
        self.fail_fb_start = False
        self.finish_rejects_finish = False
        self.yt_privacy = "public"

    def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw))
        data = kw.get("data")
        phase = data.get("upload_phase") if isinstance(data, dict) else None
        if (method, url) == ("POST", f"{G}/IGUSER/media"):
            return Resp(body={"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v25.0/C1"})
        if url == "https://rupload.facebook.com/ig-api-upload/v25.0/C1":
            return Resp(body={"success": True})
        if (method, url) == ("GET", f"{G}/C1"):
            self.ig_polls += 1
            return Resp(body={"status_code": "IN_PROGRESS" if self.ig_polls == 1 else "FINISHED"})
        if (method, url) == ("POST", f"{G}/IGUSER/media_publish"):
            return Resp(body={"id": "M1"})
        if (method, url) == ("GET", f"{G}/M1"):
            return Resp(body={"permalink": "https://www.instagram.com/reel/abc/"})
        if (method, url) == ("POST", f"{G}/M1/comments"):
            return Resp(body={"id": "IC1"})
        if (method, url) == ("POST", f"{G}/PAGE/video_reels"):
            if phase == "start":
                if self.fail_fb_start:
                    return Resp(400, {"error": {"message": "nope"}})
                return Resp(body={"video_id": "V1",
                                  "upload_url": "https://rupload.facebook.com/video-upload/v25.0/V1"})
            if phase == "finish" and self.finish_rejects_finish:
                return Resp(400, {"error": {"message": "bad upload_phase"}})
            return Resp(body={"success": True})
        if url == "https://rupload.facebook.com/video-upload/v25.0/V1":
            return Resp(body={"success": True})
        if (method, url) == ("GET", f"{G}/V1"):
            return Resp(body={"status": {"video_status": "ready"}})
        if (method, url) == ("POST", f"{G}/V1/comments"):
            return Resp(body={"id": "FC1"})
        if url == "https://oauth2.googleapis.com/token":
            return Resp(body={"access_token": "AT"})
        if url == "https://www.googleapis.com/upload/youtube/v3/videos":
            return Resp(headers={"Location": "https://upload.example/yt/1"})
        if (method, url) == ("PUT", "https://upload.example/yt/1"):
            return Resp(body={"id": "YT1", "status": {"privacyStatus": self.yt_privacy}})
        if url == "https://www.googleapis.com/youtube/v3/commentThreads":
            return Resp(body={"id": "YC1"})
        raise AssertionError(f"unexpected call {method} {url}")

    def posts_to(self, pattern):
        return [c for c in self.calls if re.search(pattern, c[1])]


ENV = {"META_PAGE_TOKEN": "PTOKEN", "IG_USER_ID": "IGUSER", "META_PAGE_ID": "PAGE",
       "YOUTUBE_CLIENT_ID": "cid", "YOUTUBE_CLIENT_SECRET": "csecret",
       "YOUTUBE_REFRESH_TOKEN": "rtoken"}


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"
        self.day = self.out / "2026-10-19"
        self.day.mkdir(parents=True)
        (self.day / "video.mp4").write_bytes(VIDEO)
        (self.day / "meta.json").write_text(json.dumps({"episode": 1, "title": "Find the missing value"}))
        (self.day / "caption.txt").write_text("Brain Teaser #1 #puzzle")
        (self.day / "answer_comment.txt").write_text("✅ Answer: 20\n\nbecause maths")
        self.web = FakeWeb()
        patches = [
            mock.patch.dict(os.environ, ENV, clear=True),
            mock.patch.object(common, "ENV_PATH", Path(self.tmp.name) / "no.env"),
            mock.patch.object(common.requests, "request", self.web),
            mock.patch.object(common, "_sleep", lambda s: None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, *extra):
        return publish_daily.main(["--date", "2026-10-19", "--out", str(self.out), *extra])

    def posted(self):
        return json.loads((self.day / "posted.json").read_text())

    def test_full_run_posts_everywhere_and_comments(self):
        self.assertEqual(self.run_main(), 0)
        p = self.posted()
        self.assertEqual({k: p[k]["id"] for k in p}, {"ig": "M1", "fb": "V1", "yt": "YT1"})
        self.assertEqual({k: p[k]["answer_comment_id"] for k in p},
                         {"ig": "IC1", "fb": "FC1", "yt": "YC1"})
        # Instagram: a Reel container with the caption, and the raw video bytes uploaded
        create = self.web.posts_to(r"/IGUSER/media$")[0][2]["data"]
        self.assertEqual((create["media_type"], create["upload_type"], create["caption"]),
                         ("REELS", "resumable", "Brain Teaser #1 #puzzle"))
        up = self.web.posts_to(r"ig-api-upload")[0][2]
        self.assertEqual(up["data"], VIDEO)
        self.assertEqual(up["headers"]["file_size"], str(len(VIDEO)))
        self.assertEqual(self.web.ig_polls, 2)  # waited once for IN_PROGRESS -> FINISHED
        # YouTube: metadata and comment
        init = self.web.posts_to(r"upload/youtube")[0][2]
        meta = json.loads(init["data"])
        self.assertEqual(meta["snippet"]["title"], "Brain Teaser #1: Find the missing value #Shorts")
        self.assertEqual(meta["status"]["privacyStatus"], "public")
        thread = self.web.posts_to(r"commentThreads")[0][2]["json"]
        self.assertEqual(thread["snippet"]["videoId"], "YT1")
        self.assertIn("Answer: 20", thread["snippet"]["topLevelComment"]["snippet"]["textOriginal"])
        # tokens never end up in a URL
        for _, url, _ in self.web.calls:
            self.assertNotIn("PTOKEN", url)

    def test_rerun_does_not_double_post(self):
        self.run_main()
        n = len(self.web.calls)
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.web.calls), n)

    def test_one_platform_failing_does_not_block_others_and_retry_fixes_it(self):
        self.web.fail_fb_start = True
        self.assertEqual(self.run_main(), 1)
        p = self.posted()
        self.assertIn("ig", p)
        self.assertIn("yt", p)
        self.assertNotIn("fb", p)
        self.web.fail_fb_start = False
        before = len(self.web.posts_to(r"/IGUSER/media$"))
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.web.posts_to(r"/IGUSER/media$")), before)  # Instagram not redone
        self.assertEqual(self.posted()["fb"]["id"], "V1")

    def test_facebook_finish_falls_back_to_complete(self):
        self.web.finish_rejects_finish = True
        self.assertEqual(self.run_main("--platforms", "fb", "--no-comment"), 0)
        phases = [c[2]["data"]["upload_phase"] for c in self.web.posts_to(r"/PAGE/video_reels")]
        self.assertEqual(phases, ["start", "finish", "complete"])

    def test_answers_only_after_no_comment(self):
        self.assertEqual(self.run_main("--no-comment"), 0)
        self.assertTrue(all(v["answer_comment_id"] is None for v in self.posted().values()))
        uploads = len(self.web.posts_to(r"/media$|video_reels|upload/youtube"))
        self.assertEqual(self.run_main("--answers-only"), 0)
        self.assertEqual(len(self.web.posts_to(r"/media$|video_reels|upload/youtube")), uploads)
        self.assertTrue(all(v["answer_comment_id"] for v in self.posted().values()))

    def test_dry_run_makes_no_calls(self):
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertEqual(self.web.calls, [])
        self.assertFalse((self.day / "posted.json").exists())

    def test_private_youtube_is_reported(self):
        self.web.yt_privacy = "private"
        self.assertEqual(self.run_main("--platforms", "yt", "--no-comment"), 0)
        self.assertEqual(self.posted()["yt"]["privacy"], "private")

    def test_state_dir_survives_a_fresh_machine(self):
        state = Path(self.tmp.name) / "state"
        self.assertEqual(self.run_main("--no-comment", "--state-dir", str(state)), 0)
        self.assertTrue((state / "2026-10-19.json").exists())
        self.assertFalse((self.day / "posted.json").exists())
        (self.day / "posted.json").unlink(missing_ok=True)
        n = len(self.web.calls)
        # new runner: the output folder is rebuilt but the state folder is restored from git
        self.assertEqual(self.run_main("--no-comment", "--state-dir", str(state)), 0)
        self.assertEqual(len(self.web.calls), n)

    def test_nothing_configured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.run_main(), 2)


if __name__ == "__main__":
    unittest.main()
