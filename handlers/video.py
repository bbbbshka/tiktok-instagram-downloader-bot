"""Handlers: PM link → video, inline @bot <link> → video."""

import logging
import os
import re

from aiogram import Router, F
from aiogram.types import (
    FSInputFile,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultVideo,
    InputTextMessageContent,
    Message,
)

from database import get_user_language, register_user
from i18n import t
from services.video_downloader import VideoDownloader, file_id_cache

logger = logging.getLogger(__name__)
router = Router()

downloader = VideoDownloader()

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------

TIKTOK_RE = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/\S+", re.IGNORECASE,
)
INSTAGRAM_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:reel|p|tv|stories)/\S+", re.IGNORECASE,
)

PLACEHOLDER_THUMB = "https://placehold.co/320x180/111111/ffffff?text=Video"


def find_video_url(text: str) -> str | None:
    for pat in (TIKTOK_RE, INSTAGRAM_RE):
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def _has_video_url(text: str) -> bool:
    return find_video_url(text) is not None


# ---------------------------------------------------------------------------
# PM: user sends a TikTok / Instagram link
# ---------------------------------------------------------------------------

@router.message(F.text.func(_has_video_url))
async def on_video_link(message: Message) -> None:
    url = find_video_url(message.text)
    if not url:
        return

    user_id = message.from_user.id
    lang = await get_user_language(user_id)

    # Fast path: if we already downloaded this URL, re-send by file_id
    cached_fid = file_id_cache.get(url)
    if cached_fid:
        try:
            await message.answer_video(video=cached_fid)
            return
        except Exception:
            file_id_cache._store.pop(url, None)

    status_msg = await message.answer(t("video_downloading", lang))

    info = await downloader.download(url)

    if not info or not info.file_path:
        reason = "video_too_large" if (info and info.file_path is None) else "video_error"
        await status_msg.edit_text(t(reason, lang))
        return

    try:
        caption = info.title[:1024] if info.title else None
        sent = await message.answer_video(
            video=FSInputFile(info.file_path),
            caption=caption,
            supports_streaming=True,
        )
        await status_msg.delete()

        # Cache file_id for instant re-sends
        if sent.video:
            file_id_cache.set(url, sent.video.file_id)
    except Exception:
        logger.exception("Failed to send video for %s", url)
        await status_msg.edit_text(t("video_error", lang))
    finally:
        if info.file_path and os.path.exists(info.file_path):
            os.remove(info.file_path)
        tmp_dir = os.path.dirname(info.file_path) if info.file_path else None
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Fallback: message without a link
# ---------------------------------------------------------------------------

@router.message(F.text)
async def on_other_text(message: Message) -> None:
    lang = await get_user_language(message.from_user.id)
    await message.answer(t("unsupported_link", lang))


# ---------------------------------------------------------------------------
# Inline mode: @bot <tiktok / insta link>
# ---------------------------------------------------------------------------

@router.inline_query()
async def on_inline_query(inline_query: InlineQuery) -> None:
    query = inline_query.query.strip()

    if not query:
        await inline_query.answer(
            [
                InlineQueryResultArticle(
                    id="hint",
                    title="Вставьте ссылку TikTok или Instagram",
                    description="Paste a TikTok or Instagram link",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            "Отправьте ссылку TikTok или Instagram для загрузки видео."
                        ),
                    ),
                ),
            ],
            cache_time=5,
            is_personal=True,
        )
        return

    url = find_video_url(query)
    if not url:
        await inline_query.answer([], cache_time=5, is_personal=True)
        return

    # Register user (inline queries don't trigger /start)
    user = inline_query.from_user
    await register_user(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )

    info = await downloader.extract_info(url)

    if not info or not info.video_url:
        await inline_query.answer(
            [
                InlineQueryResultArticle(
                    id="error",
                    title="❌ Не удалось загрузить видео",
                    description="Could not fetch this video",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Не удалось загрузить видео с этой ссылки.",
                    ),
                ),
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    thumb = info.thumbnail_url or PLACEHOLDER_THUMB
    title = info.title or "Video"

    results = [
        InlineQueryResultVideo(
            id="video_0",
            video_url=info.video_url,
            mime_type="video/mp4",
            thumbnail_url=thumb,
            title=title[:128],
            description="Нажмите, чтобы отправить / Tap to send",
        ),
    ]

    await inline_query.answer(results, cache_time=300, is_personal=False)
