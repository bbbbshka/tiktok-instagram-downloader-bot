# TikTok & Instagram Video Downloader Bot

Telegram-бот для быстрого скачивания видео из TikTok и Instagram. Работает в личных сообщениях и в **inline-режиме** прямо в любом чате.

## Возможности

- 🎬 **Скачивание видео** — отправьте ссылку TikTok или Instagram → получите видео в чат
- 🔗 **Inline-режим** — напишите `@имя_бота <ссылка>` в любом чате, чтобы отправить видео собеседнику
- ⚡ **Быстрая загрузка** — параллельное скачивание фрагментов, кеширование file_id, оптимальное качество (720p)
- 🌐 **Мультиязычность** — русский и английский
- 📦 **Кеширование** — повторная отправка того же видео мгновенно (без повторного скачивания)

### Поддерживаемые платформы

| Платформа | Форматы ссылок |
|-----------|----------------|
| TikTok | `tiktok.com`, `vm.tiktok.com`, `vt.tiktok.com`, `m.tiktok.com` |
| Instagram | Reels, посты (`/p/`), IGTV (`/tv/`), Stories |

## Установка

### 1. Клонирование
```bash
git clone https://github.com/aroslavdaskal-jpg/tiktok-instagram-downloader-bot.git
cd tiktok-instagram-downloader-bot
```

### 2. Зависимости
```bash
pip install -r requirements.txt
```

### 3. Настройка
```bash
cp .env.example .env
```

Заполните `.env`:
- `BOT_TOKEN` — токен от @BotFather
- `SUPER_ADMIN_ID` — ваш Telegram ID (от @userinfobot)

### 4. Включите inline-режим
В @BotFather:
1. `/mybots` → выберите бота
2. **Bot Settings** → **Inline Mode** → **Turn on**

### 5. Запуск
```bash
python bot.py
```

## Оптимизация скорости

Бот оптимизирован для быстрой загрузки видео:

- **Параллельные фрагменты** — yt-dlp скачивает до 8 фрагментов одновременно (`CONCURRENT_FRAGMENTS`)
- **Оптимальный формат** — выбирает 720p mp4 вместо 1080p (быстрее скачивание + отправка)
- **Кеш file_id** — если видео уже скачивалось, повторная отправка мгновенна
- **Без пост-обработки** — mp4 отправляется как есть, без лишнего перекодирования

## Структура проекта

```
tiktok-instagram-downloader-bot/
├── bot.py                  # Точка входа
├── config.py               # Конфигурация из .env
├── database.py             # SQLite (пользователи, язык)
├── i18n.py                 # Переводы (RU/EN)
├── handlers/
│   ├── start.py            # /start, выбор языка
│   └── video.py            # Скачивание видео + inline-режим
├── services/
│   └── video_downloader.py # Загрузчик видео (yt-dlp)
├── requirements.txt
├── .env.example
└── README.md
```

## Переменные окружения

| Переменная | Обязательная | Описание |
|---|---|---|
| `BOT_TOKEN` | да | Токен Telegram бота |
| `SUPER_ADMIN_ID` | нет | Telegram ID администратора |
| `MAX_VIDEO_SIZE` | нет | Макс. размер видео в байтах (по умолчанию 50 МБ) |
| `CONCURRENT_FRAGMENTS` | нет | Параллельные загрузки фрагментов (по умолчанию 8) |
| `CACHE_TTL_SECONDS` | нет | Время жизни кеша file_id (по умолчанию 3600 сек) |
