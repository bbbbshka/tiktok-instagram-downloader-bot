"""Slash-command handlers: /start and /lang."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import change_lang, save_user, user_lang
from i18n import msg

router = Router()


@router.message(Command("start"))
async def cmd_start(m: Message) -> None:
    u = m.from_user
    await save_user(u.id, u.username or "", u.first_name or "", u.last_name or "")
    lang = await user_lang(u.id)
    await m.answer(msg("hello", lang))


@router.message(Command("lang"))
async def cmd_lang(m: Message) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en"),
            ]
        ]
    )
    lang = await user_lang(m.from_user.id)
    await m.answer(msg("pick_lang", lang), reply_markup=kb)


@router.callback_query(lambda cq: cq.data and cq.data.startswith("setlang_"))
async def on_lang_pick(cq: CallbackQuery) -> None:
    picked = cq.data.split("_", 1)[1]
    await change_lang(cq.from_user.id, picked)
    await cq.message.edit_text(msg("lang_saved", picked))
    await cq.answer()
