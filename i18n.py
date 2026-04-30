"""Bilingual strings for the bot (Russian / English)."""

_STRINGS: dict[str, dict[str, str]] = {
    "hello": {
        "ru": (
            "Привет! Отправь мне ссылку на TikTok или Instagram "
            "и я скачаю видео без водяного знака.\n\n"
            "Также работаю в inline-режиме в любом чате."
        ),
        "en": (
            "Hi! Send me a TikTok or Instagram link "
            "and I'll download the video without a watermark.\n\n"
            "I also work in inline mode in any chat."
        ),
    },
    "pick_lang": {
        "ru": "Выберите язык / Choose language:",
        "en": "Choose language / Выберите язык:",
    },
    "lang_saved": {
        "ru": "Язык: Русский",
        "en": "Language: English",
    },
    "downloading": {
        "ru": "Скачиваю видео…",
        "en": "Downloading video…",
    },
    "err_download": {
        "ru": "Не удалось скачать видео. Проверьте ссылку.",
        "en": "Could not download the video. Check the link.",
    },
    "err_size": {
        "ru": "Видео слишком большое для Telegram (>50 МБ).",
        "en": "Video is too large for Telegram (>50 MB).",
    },
    "err_not_link": {
        "ru": "Отправьте ссылку на TikTok или Instagram.",
        "en": "Send me a TikTok or Instagram link.",
    },
    "err_flood": {
        "ru": "Слишком много запросов, подождите немного.",
        "en": "Too many requests, please wait.",
    },
}


def msg(key: str, lang: str = "ru", **kw: object) -> str:
    entry = _STRINGS.get(key, {})
    text = entry.get(lang, entry.get("ru", key))
    return text.format(**kw) if kw else text
