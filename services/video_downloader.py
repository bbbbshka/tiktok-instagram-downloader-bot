"""Fast video downloader for TikTok & Instagram using yt-dlp.

Speed optimisations applied:
 - Concurrent fragment downloads (CONCURRENT_FRAGMENTS env, default 8).
 - Prefer smallest adequate quality (480p/720p) — faster transfer than 1080p.
 - No post-processing when the source is already mp4.
 - In-memory file-id cache so repeated links skip the download entirely.
"""

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass

import yt_dlp

from config import MAX_VIDEO_SIZE, CONCURRENT_FRAGMENTS, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    title: str = ""
    thumbnail_url: str | None = None
    video_url: str | None = None
    duration: int | None = None
    file_path: str | None = None
    extractor: str = ""


class _FileIdCache:
    """Simple TTL cache: url → telegram file_id."""

    def __init__(self, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._store: dict[str, tuple[str, float]] = {}
        self._ttl = ttl

    def get(self, url: str) -> str | None:
        item = self._store.get(url)
        if item is None:
            return None
        file_id, ts = item
        if time.monotonic() - ts > self._ttl:
            self._store.pop(url, None)
            return None
        return file_id

    def set(self, url: str, file_id: str) -> None:
        self._store[url] = (file_id, time.monotonic())


file_id_cache = _FileIdCache()


# yt-dlp options shared between extract & download
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

# Prefer small mp4: ≤720p, smallest file, already mp4 → no re-encode
_FAST_FORMAT = (
    "best[ext=mp4][height<=720][filesize<50M]/"
    "best[ext=mp4][height<=720][filesize_approx<50M]/"
    "best[ext=mp4][height<=720]/"
    "best[ext=mp4][filesize<50M]/"
    "best[ext=mp4]/"
    "best[filesize<50M]/"
    "best"
)


class VideoDownloader:
    """Download TikTok / Instagram videos quickly."""

    async def extract_info(self, url: str) -> VideoInfo | None:
        """Extract video metadata without downloading (for inline mode)."""
        opts = {**_COMMON_OPTS, "skip_download": True, "format": _FAST_FORMAT}
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._run_extract, opts, url,
            )
            return self._parse_info(info) if info else None
        except Exception:
            logger.exception("extract_info failed for %s", url)
            return None

    async def download(self, url: str) -> VideoInfo | None:
        """Download video to a temp file. Returns VideoInfo with file_path set."""
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
        title = info.get("title") or info.get("description") or ""
        if len(title) > 200:
            title = title[:200] + "…"

        thumbnail = info.get("thumbnail") or ""
        if not thumbnail:
            thumbs = info.get("thumbnails")
            if thumbs:
                thumbnail = thumbs[-1].get("url", "")

        video_url = info.get("url") or ""
        if not video_url:
            formats = info.get("formats") or []
            mp4 = [f for f in formats if f.get("ext") == "mp4" and f.get("url")]
            if mp4:
                video_url = mp4[-1]["url"]

        return VideoInfo(
            title=title,
            thumbnail_url=thumbnail or None,
            video_url=video_url or None,
            duration=info.get("duration"),
            extractor=info.get("extractor", ""),
        )
