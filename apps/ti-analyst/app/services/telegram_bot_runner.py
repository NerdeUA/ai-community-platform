"""Standalone runner for the Telegram bot.

Started from entrypoint.sh as a separate process — completely independent of
uvicorn hot-reload. Runs until SIGTERM/SIGINT is received.

Usage (automatic, from entrypoint.sh):
    python3 -m app.services.telegram_bot_runner
"""
import asyncio
import logging
import signal

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


async def _main() -> None:
    from app.config import settings

    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKEN not set — bot runner exiting")
        return

    from app.services.telegram_bot import _build_app

    stop = asyncio.Event()

    def _handle_signal(*_):
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    from telegram import BotCommand, BotCommandScopeAllPrivateChats

    app = _build_app(settings.telegram_bot_token)
    async with app:
        await app.start()

        await app.bot.set_my_commands(
            commands=[
                BotCommand("threats", "📋 Останні загрози (за замовч. 5)"),
                BotCommand("latest",  "🔍 Деталі останньої загрози"),
                BotCommand("assets",  "🖥 Список моніторингових активів"),
                BotCommand("search",  "🔎 Пошук по CVE або назві"),
                BotCommand("start",   "ℹ️ Показати мій Telegram user ID"),
            ],
            scope=BotCommandScopeAllPrivateChats(),
        )
        logger.info("Bot commands registered")

        # Wait until Telegram's server releases any previous long-polling session.
        # On SIGKILL (container restart), the old session can persist for ~30s.
        for attempt in range(12):  # up to 60s total
            try:
                await app.bot.get_updates(offset=-1, timeout=0, limit=1)
                logger.info("Telegram session claimed after %d attempt(s)", attempt + 1)
                break
            except Exception as exc:
                if "Conflict" in type(exc).__name__ or "409" in str(exc):
                    logger.info("Previous session still active, waiting 5s... (%d/12)", attempt + 1)
                    await asyncio.sleep(5)
                else:
                    break

        await app.updater.start_polling(drop_pending_updates=False)
        logger.info("Telegram bot polling started")
        await stop.wait()
        await app.updater.stop()
        await app.stop()

    logger.info("Telegram bot stopped")


if __name__ == "__main__":
    asyncio.run(_main())
