"""Handlers: PM link → video/photos, inline @bot <link>, buttons (music, comments)."""

import logging
import os
import re

from aiogram import Router, F
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultVideo,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
    URLInputFile,
)

from database import get_user_language, register_user
from i18n import t
from services.video_downloader import (
    VideoDownloader,
    VideoInfo,
    file_id_cache,
    url_store,
)

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
YOUTUBE_RE = re.compile(
    r"https?://(?:(?:www\.|m\.)?youtube\.com/(?:watch\S+|shorts/\S+|live/\S+)|youtu\.be/\S+)", re.IGNORECASE,
)

PLACEHOLDER_THUMB = "https://placehold.co/320x180/111111/ffffff?text=Video"


def find_video_url(text: str) -> str | None:
    for pat in (TIKTOK_RE, INSTAGRAM_RE, YOUTUBE_RE):
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def _has_video_url(text: str) -> bool:
    return find_video_url(text) is not None


# ---------------------------------------------------------------------------
# Helpers: format caption & build keyboard
# ---------------------------------------------------------------------------

def _fmt_count(n: int | None) -> str:
    if n is None:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _build_caption(info: VideoInfo) -> str | None:
    return None


def _build_keyboard(url: str, info: VideoInfo, page: int = 0) -> InlineKeyboardMarkup:
    url_hash = url_store.put(url)
    row1: list[InlineKeyboardButton] = []
    row2: list[InlineKeyboardButton] = []

    # Navigation for slideshows
    if info.is_slideshow and len(info.photos) > 1:
        total = len(info.photos)
        if page > 0:
            row1.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{url_hash}:{page - 1}"))
        row1.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="noop"))
        if page < total - 1:
            row1.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{url_hash}:{page + 1}"))

    # Stats row
    if info.like_count is not None:
        row2.append(InlineKeyboardButton(text=f"❤️ {_fmt_count(info.like_count)}", callback_data="noop"))
    if info.comment_count is not None:
        row2.append(InlineKeyboardButton(text=f"💬 {_fmt_count(info.comment_count)}", callback_data=f"comments:{url_hash}"))

    # Action row
    row3: list[InlineKeyboardButton] = []
    row3.append(InlineKeyboardButton(text="🎵 Музыка", callback_data=f"music:{url_hash}"))

    rows = []
    if row1:
        rows.append(row1)
    if row2:
        rows.append(row2)
    rows.append(row3)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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

    status_msg = await message.answer(t("video_downloading", lang))

    info = await downloader.download(url)
    if not info:
        await status_msg.edit_text(t("video_error", lang))
        return

    caption = _build_caption(info)
    keyboard = _build_keyboard(url, info)

    try:
        # ---- Slideshow (photos) ----
        if info.is_slideshow and info.photos:
            await message.answer_photo(
                photo=info.photos[0],
                caption=caption,
                reply_markup=keyboard,
            )
            await status_msg.delete()
            return

        # ---- Video ----
        if not info.file_path:
            reason = "video_too_large" if info.file_path is None else "video_error"
            await status_msg.edit_text(t(reason, lang))
            return

        # Fast path: cached file_id
        cached_fid = file_id_cache.get(url)
        if cached_fid:
            try:
                await message.answer_video(
                    video=cached_fid,
                    caption=caption,
                    reply_markup=keyboard,
                )
                await status_msg.delete()
                return
            except Exception:
                file_id_cache._store.pop(url, None)

        sent = await message.answer_video(
            video=FSInputFile(info.file_path),
            caption=caption,
            supports_streaming=True,
            reply_markup=keyboard,
        )
        await status_msg.delete()

        if sent.video:
            file_id_cache.set(url, sent.video.file_id)
    except Exception:
        logger.exception("Failed to send media for %s", url)
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
# Callback: music download
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("music:"))
async def on_music_callback(callback: CallbackQuery) -> None:
    url_hash = callback.data.split(":", 1)[1]
    url = url_store.get(url_hash)
    if not url:
        await callback.answer("Ссылка не найдена, отправьте заново", show_alert=True)
        return

    lang = await get_user_language(callback.from_user.id)
    await callback.answer(t("music_downloading", lang))

    audio_path = await downloader.download_audio(url)
    if not audio_path or not os.path.exists(audio_path):
        await callback.message.answer(t("music_error", lang))
        return

    try:
        info = await downloader.extract_info(url)
        title = "Audio"
        performer = ""
        if info:
            title = info.music_title or info.title or "Audio"
            performer = info.music_author or info.author or ""

        await callback.message.answer_audio(
            audio=FSInputFile(audio_path),
            title=title[:64],
            performer=performer[:64] if performer else None,
        )
    except Exception:
        logger.exception("Failed to send audio for %s", url)
        await callback.message.answer(t("music_error", lang))
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        tmp_dir = os.path.dirname(audio_path) if audio_path else None
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Callback: show comments
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("comments:"))
async def on_comments_callback(callback: CallbackQuery) -> None:
    url_hash = callback.data.split(":", 1)[1]
    url = url_store.get(url_hash)
    if not url:
        await callback.answer("Ссылка не найдена, отправьте заново", show_alert=True)
        return

    lang = await get_user_language(callback.from_user.id)
    await callback.answer(t("comments_loading", lang))

    comments = await downloader.extract_comments(url)
    if not comments:
        key = "comments_unavailable" if "tiktok.com" in url else "comments_empty"
        await callback.message.answer(t(key, lang))
        return

    lines: list[str] = [f"💬 <b>{t('comments_title', lang)}</b>\n"]
    for i, c in enumerate(comments[:10], 1):
        likes = f"  ❤️ {_fmt_count(c['likes'])}" if c["likes"] else ""
        lines.append(f"{i}. <b>{c['author']}</b>{likes}\n{c['text']}\n")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4093] + "…"

    await callback.message.answer(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Callback: noop (stats buttons, page indicator)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ---------------------------------------------------------------------------
# Callback: slideshow page navigation
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("page:"))
async def on_page_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    url_hash = parts[1]
    page = int(parts[2])
    url = url_store.get(url_hash)
    if not url:
        await callback.answer("Ссылка не найдена", show_alert=True)
        return

    info = await downloader.extract_info(url)
    if not info or not info.is_slideshow or page >= len(info.photos):
        await callback.answer()
        return

    keyboard = _build_keyboard(url, info, page=page)
    try:
        photo_url = info.photos[page]
        caption = _build_caption(info)
        await callback.message.edit_media(
            media=InputMediaPhoto(media=photo_url, caption=caption),
            reply_markup=keyboard,
        )
        await callback.answer()
    except Exception:
        logger.exception("Slideshow navigation failed")
        await callback.answer()


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
                        message_text="Отправьте ссылку TikTok или Instagram для загрузки видео.",
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

    user = inline_query.from_user
    await register_user(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )

    info = await downloader.extract_info(url)
    if not info or (not info.video_url and not info.is_slideshow):
        await inline_query.answer(
            [
                InlineQueryResultArticle(
                    id="error",
                    title="❌ Не удалось загрузить",
                    description="Could not fetch this content",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Не удалось загрузить контент с этой ссылки.",
                    ),
                ),
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    thumb = info.thumbnail_url or PLACEHOLDER_THUMB
    title = "Отправить видео"
    caption = _build_caption(info)

    results = []

    if info.video_url:
        results.append(
            InlineQueryResultVideo(
                id="video_0",
                video_url=info.video_url,
                mime_type="video/mp4",
                thumbnail_url=thumb,
                title=title[:128],
                caption=caption,
                description="Нажмите, чтобы отправить / Tap to send",
            ),
        )

    await inline_query.answer(results, cache_time=300, is_personal=False)
