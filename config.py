import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

SUPER_ADMIN_ID: int = int(os.getenv("SUPER_ADMIN_ID", "0"))

# Maximum video file size for Telegram (bytes)
MAX_VIDEO_SIZE: int = int(os.getenv("MAX_VIDEO_SIZE", str(50 * 1024 * 1024)))

# yt-dlp concurrent fragment downloads (speeds up TikTok)
CONCURRENT_FRAGMENTS: int = int(os.getenv("CONCURRENT_FRAGMENTS", "8"))

# Cache downloaded file_ids to avoid re-downloading the same video
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
