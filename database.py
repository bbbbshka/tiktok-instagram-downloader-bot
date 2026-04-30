"""Lightweight SQLite storage for users and language preferences."""

import aiosqlite

DB_PATH = "bot.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                language  TEXT NOT NULL DEFAULT 'ru',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def register_user(
    user_id: int,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
) -> bool:
    """Register user if new. Returns True when inserted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if await cur.fetchone():
            return False
        await db.execute(
            "INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, last_name),
        )
        await db.commit()
        return True


async def get_user_language(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else "ru"


async def set_user_language(user_id: int, lang: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()
