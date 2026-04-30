"""Link handler: DM and inline-mode processing for TikTok / Instagram URLs."""

import logging
import os
import re
import time
from collections import defaultdict

from aiogram import F, Router
from aiogram.types import (
    FSInputFile,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedVideo,
    InputTextMessageContent,
    Message,
)

from config import THROTTLE_PER_MINUTE
from database import drop_video, lookup_video, save_user, store_video, user_lang
from i18n import msg
from services.downloader import Grabber

log = logging.getLogger(__name__)
router = Router()
grabber = Grabber()

# ── URL detection ──────────────────────────────────────────────────

_TT = re.compile(r"https?://(?:(?:www|vm|vt|m)\.)?tiktok\.com/\S+", re.I)
_IG = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|p|tv|stories)/\S+", re.I)


def detect_url(text: str) -> str | None:
    for rx in (_TT, _IG):
        hit = rx.search(text)
        if hit:
            return hit.group(0)
    return None


def _contains_url(text: str) -> bool:
    return detect_url(text) is not None


# ── per-user throttle ─────────────────────────────────────────────

_stamps: dict[int, list[float]] = defaultdict(list)


def _throttled(uid: int) -> bool:
    now = time.monotonic()
    history = _stamps[uid]
    _stamps[uid] = [t for t in history if now - t < 60]
    if len(_stamps[uid]) >= THROTTLE_PER_MINUTE:
        return True
    _stamps[uid].append(now)
    return False


# ── DM: user sends a link ─────────────────────────────────────────


@router.message(F.text.func(_contains_url))
async def on_link(m: Message) -> None:
    url = detect_url(m.text)
    if not url:
        return

    uid = m.from_user.id
    lang = await user_lang(uid)

    if _throttled(uid):
        await m.answer(msg("err_flood", lang))
        return

    cached = await lookup_video(url)
    if cached:
        try:
            await m.answer_video(video=cached)
            return
        except Exception:
            await drop_video(url)

    clip = await grabber.grab(url)

    if not clip or not clip.path:
        key = "err_size" if clip and clip.path is None else "err_download"
        await m.answer(msg(key, lang))
        return

    try:
        sent = await m.answer_video(
            video=FSInputFile(clip.path),
            supports_streaming=True,
        )
        if sent.video:
            await store_video(url, sent.video.file_id)
    except Exception:
        log.exception("send failed: %s", url)
        await m.answer(msg("err_download", lang))
    finally:
        if clip.path and os.path.exists(clip.path):
            os.remove(clip.path)
        parent = os.path.dirname(clip.path) if clip.path else None
        if parent and os.path.isdir(parent):
            try:
                os.rmdir(parent)
            except OSError:
                pass


# ── fallback for random text ──────────────────────────────────────


@router.message(F.text)
async def on_text(m: Message) -> None:
    lang = await user_lang(m.from_user.id)
    await m.answer(msg("err_not_link", lang))


# ── inline mode ───────────────────────────────────────────────────


async def _cache_via_pm(bot, uid: int, url: str, filepath: str) -> str | None:
    try:
        sent = await bot.send_video(
            chat_id=uid,
            video=FSInputFile(filepath),
            supports_streaming=True,
            disable_notification=True,
        )
        await bot.delete_message(chat_id=uid, message_id=sent.message_id)
        if sent.video:
            await store_video(url, sent.video.file_id)
            return sent.video.file_id
    except Exception:
        log.exception("inline upload failed: %s", url)
    return None


@router.inline_query()
async def on_inline(iq: InlineQuery) -> None:
    raw = iq.query.strip()

    if not raw:
        await iq.answer(
            [
                InlineQueryResultArticle(
                    id="tip",
                    title="Вставьте ссылку TikTok / Instagram",
                    description="Paste a TikTok or Instagram link",
                    input_message_content=InputTextMessageContent(
                        message_text="Отправь мне ссылку на TikTok или Instagram!",
                    ),
                )
            ],
            cache_time=5,
            is_personal=True,
        )
        return

    url = detect_url(raw)
    if not url:
        await iq.answer([], cache_time=5, is_personal=True)
        return

    u = iq.from_user
    await save_user(u.id, u.username or "", u.first_name or "", u.last_name or "")

    # try cache first
    cached = await lookup_video(url)
    if cached:
        try:
            await iq.answer(
                [
                    InlineQueryResultCachedVideo(
                        id="v0",
                        video_file_id=cached,
                        title="Отправить видео / Send video",
                    )
                ],
                cache_time=60,
                is_personal=False,
            )
            return
        except Exception:
            await drop_video(url)

    # download → upload via PM → return cached result
    clip = await grabber.grab(url)
    if not clip or not clip.path:
        await iq.answer(
            [
                InlineQueryResultArticle(
                    id="fail",
                    title="Не удалось скачать видео",
                    description="Could not download this video",
                    input_message_content=InputTextMessageContent(
                        message_text="Не удалось скачать видео по этой ссылке.",
                    ),
                )
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    try:
        fid = await _cache_via_pm(iq.bot, u.id, url, clip.path)
        if fid:
            await iq.answer(
                [
                    InlineQueryResultCachedVideo(
                        id="v0",
                        video_file_id=fid,
                        title=(clip.title or "Video")[:128],
                    )
                ],
                cache_time=60,
                is_personal=False,
            )
        else:
            await iq.answer(
                [
                    InlineQueryResultArticle(
                        id="nopm",
                        title="Напишите боту /start",
                        description="Write /start to the bot first, then retry",
                        input_message_content=InputTextMessageContent(
                            message_text="Напишите боту /start, затем повторите.",
                        ),
                    )
                ],
                cache_time=10,
                is_personal=True,
            )
    finally:
        if clip.path and os.path.exists(clip.path):
            os.remove(clip.path)
        parent = os.path.dirname(clip.path) if clip.path else None
        if parent and os.path.isdir(parent):
            try:
                os.rmdir(parent)
            except OSError:
                pass
