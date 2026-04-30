"""Entry point — create bot, wire routers, start polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from database import setup_tables, shutdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-25s  %(levelname)-7s  %(message)s",
)


async def main() -> None:
    from handlers.commands import router as cmd_router
    from handlers.links import router as link_router

    await setup_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(cmd_router)
    dp.include_router(link_router)

    logging.info("Bot starting…")
    try:
        await dp.start_polling(bot)
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
