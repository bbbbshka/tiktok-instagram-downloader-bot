"""Fast video/photo/audio downloader for TikTok & Instagram using yt-dlp.

Speed optimisations:
 - Concurrent fragment downloads (CONCURRENT_FRAGMENTS env, default 16).
 - Best quality mp4.
 - In-memory file-id cache so repeated links skip the download.

Features:
 - Video download with stats (likes, views, comments count, author).
 - TikTok photo slideshow (carousel) via gallery-dl fallback.
 - Audio extraction (music from TikTok).
 - Top comments extraction.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from urllib.request import Request, urlopen

import yt_dlp

from config import (
    MAX_VIDEO_SIZE,
    CONCURRENT_FRAGMENTS,
    CACHE_TTL_SECONDS,
    TIKTOK_COOKIES_FILE,
    INSTAGRAM_COOKIES_FILE,
)

logger = logging.getLogger(__name__)


def _to_int(val: object) -> int | None:
    """Safely convert a value (str or int) to int, or None."""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


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
    # dimensions
    width: int | None = None
    height: int | None = None
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

_BEST_FORMAT = (
    "best[ext=mp4][height<=1080][filesize<50M]/"
    "bestvideo[ext=mp4][height<=1080][vcodec^=avc]+bestaudio[ext=m4a]/"
    "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
    "best[ext=mp4][filesize<50M]/"
    "best[ext=mp4]/"
    "best[filesize<50M]/"
    "best"
)

_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"


def _cookies_for_url(url: str) -> str:
    """Return cookies file path for the given URL, or empty string."""
    if "tiktok.com" in url and TIKTOK_COOKIES_FILE and os.path.isfile(TIKTOK_COOKIES_FILE):
        return TIKTOK_COOKIES_FILE
    if "instagram.com" in url and INSTAGRAM_COOKIES_FILE and os.path.isfile(INSTAGRAM_COOKIES_FILE):
        return INSTAGRAM_COOKIES_FILE
    return ""


# ------------------------------------------------------------------
# Downloader
# ------------------------------------------------------------------

class VideoDownloader:
    """Download TikTok / Instagram videos, photos, audio."""

    # ---------- extract info (no download) ----------

    async def extract_info(self, url: str) -> VideoInfo | None:
        resolved = await self._resolve_url(url)
        if self._is_tiktok_photo_url(resolved):
            return await self._gallery_dl_photos(resolved, VideoInfo(extractor="tiktok"))

        normalized = self._normalize_tiktok_url(resolved)
        opts = {**_COMMON_OPTS, "skip_download": True, "format": _BEST_FORMAT}
        ck = _cookies_for_url(resolved)
        if ck:
            opts["cookiefile"] = ck
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_extract, opts, normalized,
            )
            return self._parse_info(info) if info else None
        except Exception:
            logger.exception("extract_info failed for %s", url)
            return None

    # ---------- download video ----------

    async def download(self, url: str) -> VideoInfo | None:
        resolved = await self._resolve_url(url)
        if self._is_tiktok_photo_url(resolved):
            return await self._gallery_dl_photos(resolved, VideoInfo(extractor="tiktok"))

        normalized = self._normalize_tiktok_url(resolved)
        tmp_dir = tempfile.mkdtemp(prefix="tgvid_")
        out_tpl = os.path.join(tmp_dir, "%(id)s.%(ext)s")
        opts = {
            **_COMMON_OPTS,
            "format": _BEST_FORMAT,
            "outtmpl": out_tpl,
            "merge_output_format": "mp4",
        }
        ck = _cookies_for_url(resolved)
        if ck:
            opts["cookiefile"] = ck
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_download, opts, normalized,
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
        ck = _cookies_for_url(url)
        if ck:
            opts["cookiefile"] = ck
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
        resolved = await self._resolve_url(url)
        opts = {
            **_COMMON_OPTS,
            "skip_download": True,
            "getcomments": True,
            "format": _BEST_FORMAT,
        }
        ck = _cookies_for_url(resolved)
        if ck:
            opts["cookiefile"] = ck
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_extract, opts, resolved,
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

    _TIKTOK_PHOTO_RE = re.compile(
        r"https?://(?:www\.)?tiktok\.com/@[^/]+/photo/\d+",
    )

    @staticmethod
    def _is_tiktok_photo_url(url: str) -> bool:
        return "/photo/" in url and "tiktok.com" in url

    @staticmethod
    async def _resolve_url(url: str) -> str:
        """Resolve TikTok short links to their final URL."""
        if "tiktok.com" not in url or ("/video/" in url or "/photo/" in url):
            return url
        try:
            req = Request(url, headers={"User-Agent": _COMMON_OPTS["http_headers"]["User-Agent"]})
            final = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: urlopen(req, timeout=20).geturl(),
            )
            if final.rstrip("/") in ("https://www.tiktok.com", "https://www.tiktok.com/?_r=1"):
                logger.warning("Short link %s resolved to homepage (expired?)", url)
                return url
            return final
        except Exception:
            logger.exception("Failed to resolve short url %s", url)
            return url

    @staticmethod
    def _normalize_tiktok_url(url: str) -> str:
        """Convert /photo/ TikTok URLs to /video/ so yt-dlp can handle them."""
        if "tiktok.com" in url and "/photo/" in url:
            return url.replace("/photo/", "/video/").split("?", 1)[0]
        return url

    async def download_photos(self, url: str) -> list[str]:
        """Download photos via gallery-dl to temp files, return list of file paths."""
        resolved = await self._resolve_url(url)
        tmp_dir = tempfile.mkdtemp(prefix="tgpho_")
        cmd = [
            sys.executable, "-m", "gallery_dl",
            "--dest", tmp_dir,
            "--filename", "{num:>02}.{extension}",
        ]
        ck = _cookies_for_url(resolved)
        if ck:
            cmd.extend(["--cookies", ck])
        cmd.append(resolved)
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=120),
            )
            if proc.returncode != 0:
                logger.warning("gallery-dl download failed for %s: %s", url, proc.stderr[:500])
                return []
            paths: list[str] = []
            for root, _dirs, files in os.walk(tmp_dir):
                for f in sorted(files):
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        paths.append(os.path.join(root, f))
            return paths
        except Exception:
            logger.exception("download_photos failed for %s", url)
            return []

    async def _gallery_dl_photos(self, url: str, base_info: VideoInfo) -> VideoInfo:
        """Use gallery-dl to extract photo URLs from TikTok photo posts."""
        try:
            cmd = [sys.executable, "-m", "gallery_dl", "--dump-json"]
            ck = _cookies_for_url(url)
            if ck:
                cmd.extend(["--cookies", ck])
            cmd.append(url)
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=60,
                ),
            )
            if proc.returncode != 0:
                logger.warning("gallery-dl failed for %s: %s", url, proc.stderr[:500])
                return base_info

            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                return base_info

            if not isinstance(data, list):
                return base_info

            photos: list[str] = []
            for item in data:
                if not isinstance(item, list) or len(item) < 3:
                    continue
                file_url = item[1] if isinstance(item[1], str) else None
                meta = item[2] if isinstance(item[2], dict) else {}
                ext = meta.get("extension", "")
                if file_url and ext in ("jpg", "jpeg", "png", "webp"):
                    photos.append(file_url)

            if photos:
                base_info.is_slideshow = True
                base_info.photos = photos
                for item in data:
                    if not isinstance(item, list) or len(item) < 3:
                        continue
                    meta = item[2] if isinstance(item[2], dict) else {}
                    s = meta.get("stats")
                    if isinstance(s, dict) and "diggCount" in s:
                        base_info.like_count = _to_int(s.get("diggCount"))
                        base_info.view_count = _to_int(s.get("playCount"))
                        base_info.comment_count = _to_int(s.get("commentCount"))
                        break
            return base_info
        except Exception:
            logger.exception("gallery-dl fallback failed for %s", url)
            return base_info

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

        w = info.get("width")
        h = info.get("height")
        if not w or not h:
            rd = info.get("requested_downloads") or []
            if rd:
                w = w or rd[0].get("width")
                h = h or rd[0].get("height")

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
            width=_to_int(w),
            height=_to_int(h),
            music_title=track,
            music_author=artist,
        )
