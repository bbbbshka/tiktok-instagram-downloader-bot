"""Fast video/photo/audio downloader for TikTok & Instagram using yt-dlp.

Speed optimisations:
 - Concurrent fragment downloads (CONCURRENT_FRAGMENTS env, default 8).
 - Prefer 720p mp4 — faster transfer than 1080p.
 - In-memory file-id cache so repeated links skip the download.

Features:
 - Video download with stats (likes, views, comments count, author).
 - TikTok photo slideshow (carousel) → list of image URLs.
 - Audio extraction (music from TikTok).
 - Top comments extraction.
"""

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field

import yt_dlp

from config import MAX_VIDEO_SIZE, CONCURRENT_FRAGMENTS, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------

@dataclass
class VideoInfo:
    title: str = ""
    thumbnail_url: str | None = None
    video_url: str | None = None
    duration: int | None = None
    file_path: str | None = None
    extractor: str = ""
    # stats
    author: str = ""
    like_count: int | None = None
    view_count: int | None = None
    comment_count: int | None = None
    # photos (TikTok slideshow)
    photos: list[str] = field(default_factory=list)
    is_slideshow: bool = False
    # music
    music_title: str = ""
    music_author: str = ""
    # comments
    comments: list[dict] = field(default_factory=list)


# ------------------------------------------------------------------
# Caches
# ------------------------------------------------------------------

class _FileIdCache:
    """TTL cache: url → telegram file_id (or list of file_ids for albums)."""

    def __init__(self, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._store: dict[str, tuple[object, float]] = {}
        self._ttl = ttl

    def get(self, url: str) -> object | None:
        item = self._store.get(url)
        if item is None:
            return None
        value, ts = item
        if time.monotonic() - ts > self._ttl:
            self._store.pop(url, None)
            return None
        return value

    def set(self, url: str, value: object) -> None:
        self._store[url] = (value, time.monotonic())


file_id_cache = _FileIdCache()


class _UrlStore:
    """Map short hash → original URL for callback data (64-byte limit)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def put(self, url: str) -> str:
        h = hashlib.md5(url.encode()).hexdigest()[:10]
        self._store[h] = url
        return h

    def get(self, h: str) -> str | None:
        return self._store.get(h)


url_store = _UrlStore()

# ------------------------------------------------------------------
# yt-dlp options
# ------------------------------------------------------------------

_COMMON_OPTS: dict = {
    "quiet": True,
    "no_warnings": True,
    "no_color": True,
    "socket_timeout": 20,
    "retries": 2,
    "extractor_retries": 2,
    "concurrent_fragment_downloads": CONCURRENT_FRAGMENTS,
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    },
}

_FAST_FORMAT = (
    "best[ext=mp4][height<=720][filesize<50M]/"
    "best[ext=mp4][height<=720][filesize_approx<50M]/"
    "best[ext=mp4][height<=720]/"
    "best[ext=mp4][filesize<50M]/"
    "best[ext=mp4]/"
    "best[filesize<50M]/"
    "best"
)

_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"


# ------------------------------------------------------------------
# Downloader
# ------------------------------------------------------------------

class VideoDownloader:
    """Download TikTok / Instagram videos, photos, audio."""

    # ---------- extract info (no download) ----------

    async def extract_info(self, url: str) -> VideoInfo | None:
        opts = {**_COMMON_OPTS, "skip_download": True, "format": _FAST_FORMAT}
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_extract, opts, url,
            )
            return self._parse_info(info) if info else None
        except Exception:
            logger.exception("extract_info failed for %s", url)
            return None

    # ---------- download video ----------

    async def download(self, url: str) -> VideoInfo | None:
        tmp_dir = tempfile.mkdtemp(prefix="tgvid_")
        out_tpl = os.path.join(tmp_dir, "%(id)s.%(ext)s")
        opts = {
            **_COMMON_OPTS,
            "format": _FAST_FORMAT,
            "outtmpl": out_tpl,
            "merge_output_format": "mp4",
        }
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_download, opts, url,
            )
            if info is None:
                return None

            vi = self._parse_info(info)

            # If it's a slideshow, no video file needed
            if vi.is_slideshow:
                return vi

            downloaded = info.get("requested_downloads") or []
            if downloaded:
                vi.file_path = downloaded[0].get("filepath")
            else:
                for fname in os.listdir(tmp_dir):
                    vi.file_path = os.path.join(tmp_dir, fname)
                    break

            if vi.file_path and os.path.exists(vi.file_path):
                size = os.path.getsize(vi.file_path)
                if size > MAX_VIDEO_SIZE:
                    logger.warning("Video too large (%d bytes)", size)
                    os.remove(vi.file_path)
                    vi.file_path = None

            return vi
        except Exception:
            logger.exception("download failed for %s", url)
            return None

    # ---------- download audio only ----------

    async def download_audio(self, url: str) -> str | None:
        """Download audio track and return path to file, or None."""
        tmp_dir = tempfile.mkdtemp(prefix="tgaud_")
        out_tpl = os.path.join(tmp_dir, "%(id)s.%(ext)s")
        opts = {
            **_COMMON_OPTS,
            "format": _AUDIO_FORMAT,
            "outtmpl": out_tpl,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
            ],
        }
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_download, opts, url,
            )
            if info is None:
                return None

            downloaded = info.get("requested_downloads") or []
            if downloaded:
                return downloaded[0].get("filepath")

            for fname in os.listdir(tmp_dir):
                return os.path.join(tmp_dir, fname)
            return None
        except Exception:
            logger.exception("download_audio failed for %s", url)
            return None

    # ---------- extract comments ----------

    async def extract_comments(self, url: str) -> list[dict]:
        """Return top comments: [{'author': str, 'text': str, 'likes': int}]."""
        opts = {
            **_COMMON_OPTS,
            "skip_download": True,
            "getcomments": True,
            "format": _FAST_FORMAT,
        }
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_extract, opts, url,
            )
            if not info:
                return []
            raw = info.get("comments") or []
            result = []
            for c in raw[:20]:
                result.append({
                    "author": c.get("author") or c.get("author_id") or "?",
                    "text": (c.get("text") or "")[:300],
                    "likes": c.get("like_count") or 0,
                })
            result.sort(key=lambda x: x["likes"], reverse=True)
            return result[:10]
        except Exception:
            logger.exception("extract_comments failed for %s", url)
            return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_extract(opts: dict, url: str) -> dict | None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    @staticmethod
    def _run_download(opts: dict, url: str) -> dict | None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    @staticmethod
    def _parse_info(info: dict) -> VideoInfo:
        # Check if this is a playlist (TikTok slideshow)
        is_slideshow = False
        photos: list[str] = []
        entries = info.get("entries")

        if info.get("_type") == "playlist" and entries:
            entries = list(entries)
            image_urls = []
            for e in entries:
                url = e.get("url") or ""
                ext = e.get("ext") or ""
                if ext in ("jpg", "jpeg", "png", "webp") or "image" in (e.get("format") or ""):
                    image_urls.append(url)
            if image_urls:
                is_slideshow = True
                photos = image_urls
                # Use first entry for metadata
                if entries:
                    info = {**info, **entries[0]}

        title = info.get("title") or info.get("description") or ""
        if len(title) > 200:
            title = title[:200] + "…"

        thumbnail = info.get("thumbnail") or ""
        if not thumbnail:
            thumbs = info.get("thumbnails")
            if thumbs:
                thumbnail = thumbs[-1].get("url", "")

        video_url = info.get("url") or ""
        if not video_url and not is_slideshow:
            formats = info.get("formats") or []
            mp4 = [f for f in formats if f.get("ext") == "mp4" and f.get("url")]
            if mp4:
                video_url = mp4[-1]["url"]

        author = info.get("uploader") or info.get("creator") or info.get("channel") or ""

        track = info.get("track") or ""
        artist = info.get("artist") or ""

        return VideoInfo(
            title=title,
            thumbnail_url=thumbnail or None,
            video_url=video_url or None,
            duration=info.get("duration"),
            extractor=info.get("extractor", ""),
            author=author,
            like_count=info.get("like_count"),
            view_count=info.get("view_count"),
            comment_count=info.get("comment_count"),
            photos=photos,
            is_slideshow=is_slideshow,
            music_title=track,
            music_author=artist,
        )
