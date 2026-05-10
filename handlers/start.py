"""Handlers for /start and language selection, including deep-link actions."""

import logging
import os

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from database import register_user, get_user_language, set_user_language
from i18n import t
from services.video_downloader import VideoDownloader, url_store

logger = logging.getLogger(__name__)
router = Router()
downloader = VideoDownloader()


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
            ],
        ],
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    user = message.from_user
    await register_user(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )

    args = command.args or ""
    lang = await get_user_language(user.id)

    if args.startswith("music_"):
        url_hash = args[6:]
        url = url_store.get(url_hash)
        if not url:
            await message.answer(t("video_error", lang))
            return
        await message.answer(t("music_downloading", lang))
        audio_path = await downloader.download_audio(url)
        if not audio_path or not os.path.exists(audio_path):
            await message.answer(t("music_error", lang))
            return
        try:
            info = await downloader.extract_info(url)
            title = "Audio"
            performer = ""
            if info:
                title = info.music_title or info.title or "Audio"
                performer = info.music_author or info.author or ""
            await message.answer_audio(
                audio=FSInputFile(audio_path),
                title=title[:64],
                performer=performer[:64] if performer else None,
            )
        except Exception:
            logger.exception("Deep-link music failed for %s", url)
            await message.answer(t("music_error", lang))
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            tmp_dir = os.path.dirname(audio_path) if audio_path else None
            if tmp_dir and os.path.isdir(tmp_dir):
                try:
                    os.rmdir(tmp_dir)
                except OSError:
                    pass
        return

    if args.startswith("comments_"):
        url_hash = args[9:]
        url = url_store.get(url_hash)
        if not url:
            await message.answer(t("video_error", lang))
            return
        await message.answer(t("comments_loading", lang))
        comments = await downloader.extract_comments(url)
        if not comments:
            key = "comments_unavailable" if "tiktok.com" in url else "comments_empty"
            await message.answer(t(key, lang))
            return
        from handlers.video import _fmt_count
        lines: list[str] = [f"💬 <b>{t('comments_title', lang)}</b>\n"]
        for i, c in enumerate(comments[:10], 1):
            likes = f"  ❤️ {_fmt_count(c['likes'])}" if c["likes"] else ""
            lines.append(f"{i}. <b>{c['author']}</b>{likes}\n{c['text']}\n")
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4093] + "…"
        await message.answer(text, parse_mode="HTML")
        return

    lang = await get_user_language(user.id)
    await message.answer(t("welcome", lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("lang_"))
async def on_language_select(callback: CallbackQuery) -> None:
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id

    await register_user(
        user_id=user_id,
        username=callback.from_user.username or "",
        first_name=callback.from_user.first_name or "",
        last_name=callback.from_user.last_name or "",
    )
    await set_user_language(user_id, lang)

    await callback.answer(t("language_set", lang))
    await callback.message.answer(t("welcome", lang), parse_mode="HTML")
    await callback.message.delete()
