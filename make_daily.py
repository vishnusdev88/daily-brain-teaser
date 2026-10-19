"""Make today's brain-teaser video plus its caption and answer comment.

    python3 make_daily.py                    # today
    python3 make_daily.py --date 2026-10-19  # a specific day
    python3 make_daily.py --handle @mypage --music track.mp3

Output goes to out/<date>/: video.mp4, cover.png, caption.txt, answer_comment.txt, meta.json
"""
import argparse
import json
from datetime import date
from pathlib import Path

from teasers import make_teaser
from videomaker import render_video

START = date(2026, 10, 19)  # episode #1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="ISO date, default today")
    ap.add_argument("--episode", type=int, help="override the episode number")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    ap.add_argument("--handle", default="", help="shown under the header, e.g. @mypage")
    ap.add_argument("--music", help="optional audio file (mp3/m4a/wav)")
    ap.add_argument("--countdown", type=int, default=10, help="seconds to think")
    args = ap.parse_args()

    d = date.fromisoformat(args.date) if args.date else date.today()
    episode = args.episode or max(1, (d - START).days + 1)
    teaser = make_teaser(d)
    folder = Path(args.out) / d.isoformat()

    paths = render_video(teaser, episode, folder, handle=args.handle,
                         music=args.music, countdown=args.countdown)

    caption = (f"🧠 Brain Teaser #{episode}: can you solve it in {args.countdown} seconds?\n\n"
               "Drop your answer below 👇 The solution will be in the comments!\n\n"
               "#brainteaser #puzzle #maths #riddles #iqtest #mindgames #reels")
    answer = f"✅ Answer: {teaser.answer}\n\n{teaser.explanation}"

    (folder / "caption.txt").write_text(caption, encoding="utf-8")
    (folder / "answer_comment.txt").write_text(answer, encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(
        {"date": d.isoformat(), "episode": episode, **teaser.to_dict()},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Episode #{episode} ({teaser.kind}) -> {folder}")
    print(f"  video:  {paths['video']}")
    print(f"  answer: {teaser.answer}")


if __name__ == "__main__":
    main()
