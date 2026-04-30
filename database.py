"""Async SQLite database layer.

Manages user profiles, language preferences, and a persistent
Telegram file_id cache so repeated video requests are instant.
"""

import logging
import time

import aiosqlite

from config import DATABASE_PATH, CACHE_LIFETIME

log = logging.getLogger(__name__)

_conn: aiosqlite.Connection | None = None


async def connection() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(DATABASE_PATH)
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


async def shutdown() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def setup_tables() -> None:
    db = await connection()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            uid        INTEGER PRIMARY KEY,
            username   TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name  TEXT DEFAULT '',
            lang       TEXT DEFAULT 'ru',
            joined_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS video_cache (
            url        TEXT PRIMARY KEY,
            file_id    TEXT NOT NULL,
            saved_at   REAL NOT NULL
        )
        """
    )
    await db.commit()


# ── users ──────────────────────────────────────────────────────────


async def save_user(
    uid: int, username: str = "", first_name: str = "", last_name: str = ""
) -> bool:
    db = await connection()
    row = await (await db.execute("SELECT 1 FROM users WHERE uid=?", (uid,))).fetchone()
    if row:
        return False
    await db.execute(
        "INSERT INTO users (uid, username, first_name, last_name) VALUES (?,?,?,?)",
        (uid, username, first_name, last_name),
    )
    await db.commit()
    return True


async def user_lang(uid: int) -> str:
    db = await connection()
    row = await (
        await db.execute("SELECT lang FROM users WHERE uid=?", (uid,))
    ).fetchone()
    return row[0] if row else "ru"


async def change_lang(uid: int, lang: str) -> None:
    db = await connection()
    await db.execute("UPDATE users SET lang=? WHERE uid=?", (lang, uid))
    await db.commit()


# ── video cache ────────────────────────────────────────────────────


async def lookup_video(url: str) -> str | None:
    db = await connection()
    row = await (
        await db.execute(
            "SELECT file_id, saved_at FROM video_cache WHERE url=?", (url,)
        )
    ).fetchone()
    if row is None:
        return None
    fid, ts = row
    if time.time() - ts > CACHE_LIFETIME:
        await db.execute("DELETE FROM video_cache WHERE url=?", (url,))
        await db.commit()
        return None
    return fid


async def store_video(url: str, file_id: str) -> None:
    db = await connection()
    await db.execute(
        "INSERT OR REPLACE INTO video_cache (url, file_id, saved_at) VALUES (?,?,?)",
        (url, file_id, time.time()),
    )
    await db.commit()


async def drop_video(url: str) -> None:
    db = await connection()
    await db.execute("DELETE FROM video_cache WHERE url=?", (url,))
    await db.commit()
