TRANSLATIONS: dict[str, dict[str, str]] = {
    "welcome": {
        "ru": (
            "👋 Привет! Я бот для скачивания видео.\n\n"
            "🎬 Отправь мне ссылку на <b>TikTok</b> или <b>Instagram</b> — "
            "и я пришлю видео прямо в чат.\n\n"
            "🔗 <b>Inline-режим</b>: напиши <code>@имя_бота ссылку</code> "
            "в любом чате, чтобы отправить видео собеседнику."
        ),
        "en": (
            "👋 Hi! I'm a video downloader bot.\n\n"
            "🎬 Send me a <b>TikTok</b> or <b>Instagram</b> link — "
            "and I'll send the video right here.\n\n"
            "🔗 <b>Inline mode</b>: type <code>@botname link</code> "
            "in any chat to send a video to your conversation."
        ),
    },
    "video_downloading": {
        "ru": "⏳ Загружаю видео…",
        "en": "⏳ Downloading video…",
    },
    "video_error": {
        "ru": "❌ Не удалось загрузить видео. Проверьте ссылку и попробуйте снова.",
        "en": "❌ Failed to download the video. Check the link and try again.",
    },
    "video_too_large": {
        "ru": "❌ Видео слишком большое (>50 МБ) для отправки в Telegram.",
        "en": "❌ Video is too large (>50 MB) to send via Telegram.",
    },
    "unsupported_link": {
        "ru": "🤷 Отправьте ссылку на TikTok или Instagram, чтобы я скачал видео.",
        "en": "🤷 Send a TikTok or Instagram link so I can download the video.",
    },
    "choose_language": {
        "ru": "🌐 Выберите язык / Choose language:",
        "en": "🌐 Choose language / Выберите язык:",
    },
    "language_set": {
        "ru": "✅ Язык установлен: Русский",
        "en": "✅ Language set: English",
    },
}


def t(key: str, lang: str = "ru", **kwargs: object) -> str:
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang, entry.get("ru", key))
    if kwargs:
        text = text.format(**kwargs)
    return text
