"""Render a brain teaser as a vertical 1080x1920 countdown video (Pillow + ffmpeg).

Layout keeps all text inside Instagram's safe zone (clear of the top bar and the
caption / buttons at the bottom of a Reel).
"""
from __future__ import annotations

import math
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

W, H, FPS = 1080, 1920, 10
TAIL_SECONDS = 3  # the "answer in the comments" card at the end

FONT_PATHS = [
    str(Path(__file__).resolve().parent / "fonts" / "DejaVuSans-Bold.ttf"),  # bundled copy
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
FONT_PATH = next((p for p in FONT_PATHS if Path(p).exists()), None)
if FONT_PATH is None:
    raise RuntimeError("DejaVuSans-Bold.ttf not found - set FONT_PATH in videomaker.py")

# (gradient top, gradient bottom, accent)
PALETTES = [
    ("#1b1464", "#6a11cb", "#ffd166"),
    ("#0f2027", "#2c5364", "#06d6a0"),
    ("#2b1055", "#7597de", "#ffb703"),
    ("#141e30", "#243b55", "#ff6b6b"),
    ("#0f0c29", "#302b63", "#4cc9f0"),
]

CARD = (70, 470, 1010, 1290)      # x0, y0, x1, y1
URGENT = (255, 107, 107)          # timer colour for the last 3 seconds


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split(" "):
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, paragraphs, max_w, max_h):
    """Largest font size whose wrapped paragraphs fit the box."""
    for size in range(84, 35, -4):
        font = _font(size)
        line_h, gap = int(size * 1.28), int(size * 0.55)
        blocks = [_wrap(draw, p, font, max_w) for p in paragraphs]
        total = sum(len(b) for b in blocks) * line_h + gap * (len(blocks) - 1)
        if total <= max_h:
            break
    return font, blocks, line_h, gap, total


def _overlay_rect(img, box, radius, rgba):
    """Alpha-blended rounded rectangle (ImageDraw alone would not blend)."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=rgba)
    return Image.alpha_composite(img, layer)


def _base_frame(teaser, episode, palette, handle):
    c1, c2, accent = (ImageColor.getrgb(c) for c in palette)
    grad = Image.linear_gradient("L").resize((W, H))
    img = ImageOps.colorize(grad, black=c1, white=c2).convert("RGBA")

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        CARD, radius=48, fill=(255, 255, 255, 28), outline=(255, 255, 255, 80), width=3)
    img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)

    d.text((W / 2, 235), "DAILY BRAIN TEASER", font=_font(46), fill=accent, anchor="ma")
    d.text((W / 2, 295), f"#{episode}", font=_font(120), fill="white", anchor="ma")
    if handle:
        d.text((W / 2, 425), handle, font=_font(34), fill=(255, 255, 255, 190), anchor="ma")

    x0, y0, x1, y1 = CARD
    d.text((W / 2, y0 + 55), teaser.title, font=_font(54), fill=accent, anchor="ma")
    d.line((W / 2 - 150, y0 + 135, W / 2 + 150, y0 + 135), fill=accent, width=4)

    top, bottom = y0 + 165, y1 - 45
    font, blocks, line_h, gap, total = _fit(d, teaser.body, (x1 - x0) - 120, bottom - top)
    y = top + (bottom - top - total) / 2
    for block in blocks:
        for line in block:
            d.text((W / 2, y), line, font=font, fill="white", anchor="ma")
            y += line_h
        y += gap
    return img, accent


def _timer_frame(base, accent, t, countdown):
    img = base.copy()
    if t < countdown:
        remaining = countdown - t
        shown = math.ceil(remaining)
        colour = URGENT if shown <= 3 else "white"
        d = ImageDraw.Draw(img)
        d.text((W / 2, 1320), str(shown), font=_font(120), fill=colour, anchor="ma")
        img = _overlay_rect(img, (140, 1470, 940, 1496), 13, (255, 255, 255, 60))
        bar_w = max(int(800 * remaining / countdown), 26)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((140, 1470, 140 + bar_w, 1496), radius=13, fill=colour if shown <= 3 else accent)
    else:
        bounce = int(8 * math.sin((t - countdown) * 2 * math.pi * 1.5))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((90, 1330 + bounce, 990, 1480 + bounce), radius=40, fill=accent)
        label = "ANSWER IN THE COMMENTS ▼"
        for size in range(60, 33, -2):
            if d.textlength(label, font=_font(size)) <= 820:
                break
        d.text((W / 2, 1405 + bounce), label, font=_font(size), fill=(20, 20, 40), anchor="mm")
    return img.convert("RGB")


def render_video(teaser, episode, out_dir, handle="", music=None, countdown=10):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    palette = PALETTES[episode % len(PALETTES)]
    base, accent = _base_frame(teaser, episode, palette, handle)

    total_s = countdown + TAIL_SECONDS
    video, cover = out_dir / "video.mp4", out_dir / "cover.png"
    _timer_frame(base, accent, 0, countdown).save(cover)

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-"]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music),
                "-af", f"afade=t=out:st={total_s - 1}:d=1"]
    else:  # silent AAC track so every platform sees an audio stream
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    # Facebook's Reels spec: fixed 30 fps, GOP of 2 s, AAC-LC 48 kHz stereo >= 128 kbps
    cmd += ["-map", "0:v", "-map", "1:a", "-t", str(total_s), "-r", "30",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-g", "60", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
            "-movflags", "+faststart", str(video)]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for i in range(total_s * FPS):
        proc.stdin.write(_timer_frame(base, accent, i / FPS, countdown).tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {err}")
    return {"video": video, "cover": cover}
