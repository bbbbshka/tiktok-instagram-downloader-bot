"""Handlers for /start and language selection."""

import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import register_user, get_user_language, set_user_language
from i18n import t

logger = logging.getLogger(__name__)
router = Router()


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
async def cmd_start(message: Message) -> None:
    user = message.from_user
    is_new = await register_user(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )
    if is_new:
        await message.answer(t("choose_language"), reply_markup=language_keyboard())
    else:
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
