"""Video grabber powered by yt-dlp.

Downloads TikTok and Instagram clips watermark-free, picks a
compact 720p mp4 when possible to keep transfer times short.
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass

import yt_dlp

from config import VIDEO_SIZE_LIMIT, DOWNLOAD_WORKERS

log = logging.getLogger(__name__)


@dataclass
class Clip:
    title: str = ""
    thumb: str | None = None
    direct_url: str | None = None
    seconds: int | None = None
    path: str | None = None
    source: str = ""


_YDL_BASE: dict = {
    "quiet": True,
    "no_warnings": True,
    "no_color": True,
    "socket_timeout": 20,
    "retries": 3,
    "extractor_retries": 3,
    "concurrent_fragment_downloads": DOWNLOAD_WORKERS,
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    },
}

_QUALITY = (
    "best[ext=mp4][height<=720][filesize<50M]/"
    "best[ext=mp4][height<=720][filesize_approx<50M]/"
    "best[ext=mp4][height<=720]/"
    "best[ext=mp4][filesize<50M]/"
    "best[ext=mp4]/"
    "best[filesize<50M]/"
    "best"
)


def _extract(opts: dict, url: str) -> dict | None:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _fetch(opts: dict, url: str) -> dict | None:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=True)


def _build_clip(raw: dict) -> Clip:
    name = raw.get("title") or raw.get("description") or ""
    if len(name) > 200:
        name = name[:197] + "..."

    thumb = raw.get("thumbnail") or ""
    if not thumb:
        previews = raw.get("thumbnails")
        if previews:
            thumb = previews[-1].get("url", "")

    stream = raw.get("url") or ""
    if not stream:
        fmts = raw.get("formats") or []
        candidates = [f for f in fmts if f.get("ext") == "mp4" and f.get("url")]
        if candidates:
            stream = candidates[-1]["url"]

    return Clip(
        title=name,
        thumb=thumb or None,
        direct_url=stream or None,
        seconds=raw.get("duration"),
        source=raw.get("extractor", ""),
    )


class Grabber:
    """High-level async interface for downloading social-media videos."""

    async def peek(self, url: str) -> Clip | None:
        opts = {**_YDL_BASE, "skip_download": True, "format": _QUALITY}
        try:
            raw = await asyncio.to_thread(_extract, opts, url)
            return _build_clip(raw) if raw else None
        except Exception:
            log.exception("peek failed: %s", url)
            return None

    async def grab(self, url: str) -> Clip | None:
        work_dir = tempfile.mkdtemp(prefix="vid_")
        opts = {
            **_YDL_BASE,
            "format": _QUALITY,
            "outtmpl": os.path.join(work_dir, "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
        }
        try:
            raw = await asyncio.to_thread(_fetch, opts, url)
            if raw is None:
                return None

            clip = _build_clip(raw)

            downloads = raw.get("requested_downloads") or []
            if downloads:
                clip.path = downloads[0].get("filepath")
            else:
                for name in os.listdir(work_dir):
                    clip.path = os.path.join(work_dir, name)
                    break

            if clip.path and os.path.exists(clip.path):
                if os.path.getsize(clip.path) > VIDEO_SIZE_LIMIT:
                    log.warning("file too big: %s", clip.path)
                    os.remove(clip.path)
                    clip.path = None

            return clip
        except Exception:
            log.exception("grab failed: %s", url)
            return None
