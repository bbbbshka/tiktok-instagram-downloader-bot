"""Tests for the database layer."""

import os
import pytest
import pytest_asyncio

# Override DB path before importing database module
os.environ["DATABASE_PATH"] = ":memory:"

from database import (  # noqa: E402
    change_lang,
    drop_video,
    lookup_video,
    save_user,
    setup_tables,
    shutdown,
    store_video,
    user_lang,
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_db():
    await shutdown()
    await setup_tables()
    yield
    await shutdown()


class TestUsers:
    @pytest.mark.asyncio
    async def test_new_user(self):
        ok = await save_user(1, "bob", "Bob", "Smith")
        assert ok is True

    @pytest.mark.asyncio
    async def test_duplicate_user(self):
        await save_user(2, "ann", "Ann", "")
        ok = await save_user(2, "ann", "Ann", "")
        assert ok is False

    @pytest.mark.asyncio
    async def test_default_lang(self):
        await save_user(3)
        assert await user_lang(3) == "ru"

    @pytest.mark.asyncio
    async def test_switch_lang(self):
        await save_user(4)
        await change_lang(4, "en")
        assert await user_lang(4) == "en"

    @pytest.mark.asyncio
    async def test_unknown_user_lang(self):
        assert await user_lang(9999) == "ru"


class TestCache:
    @pytest.mark.asyncio
    async def test_store_and_get(self):
        await store_video("https://example.com/v1", "fid_aaa")
        assert await lookup_video("https://example.com/v1") == "fid_aaa"

    @pytest.mark.asyncio
    async def test_missing(self):
        assert await lookup_video("https://nope.com") is None

    @pytest.mark.asyncio
    async def test_drop(self):
        await store_video("https://example.com/v2", "fid_bbb")
        await drop_video("https://example.com/v2")
        assert await lookup_video("https://example.com/v2") is None

    @pytest.mark.asyncio
    async def test_overwrite(self):
        await store_video("https://example.com/v3", "old")
        await store_video("https://example.com/v3", "new")
        assert await lookup_video("https://example.com/v3") == "new"
