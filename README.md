# TikTok & Instagram Video Downloader Bot

Telegram-бот для скачивания видео из TikTok и Instagram **без водяных знаков**.

## Возможности

- Скачивание видео TikTok без ватермарки
- Скачивание Instagram Reels, постов, IGTV, Stories
- Inline-режим — отправляй видео прямо из любого чата
- Кеш видео в SQLite — повторные запросы мгновенные
- Rate-limiting — защита от спама
- Поддержка русского и английского языков

## Быстрый старт

### Без Docker

```bash
git clone https://github.com/bbbbshka/tiktok-instagram-downloader-bot.git
cd tiktok-instagram-downloader-bot

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Заполни BOT_TOKEN и ADMIN_ID в .env

python bot.py
```

### Docker

```bash
cp .env.example .env
# Заполни BOT_TOKEN и ADMIN_ID

docker compose up -d
```

## Настройка

| Переменная | Описание | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | Токен от @BotFather | — |
| `ADMIN_ID` | Telegram ID админа | — |
| `DATABASE_PATH` | Путь к SQLite файлу | `bot.db` |
| `VIDEO_SIZE_LIMIT` | Макс. размер видео (байт) | `52428800` |
| `CACHE_LIFETIME` | TTL кеша (сек) | `3600` |
| `THROTTLE_PER_MINUTE` | Лимит запросов/мин на юзера | `10` |

## Тестирование

```bash
pip install ruff pytest pytest-asyncio
pytest tests/ -v
ruff check .
```

## Команды бота

- `/start` — приветствие
- `/lang` — сменить язык (RU / EN)
- Отправь ссылку — получи видео
