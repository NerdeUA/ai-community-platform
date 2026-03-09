"""
One-time Telegram login to create a persistent user session.

Run once inside the container:
    docker exec -it <ti-analyst-container> python3 -m app.services.telegram_login
"""
import asyncio
import sys

_SESSION_PATH = "/app/.telegram_session"


async def main():
    try:
        from telethon import TelegramClient
    except ImportError:
        print("ERROR: telethon not installed. Run: pip install telethon")
        sys.exit(1)

    from app.config import settings

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        print("ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env.local")
        sys.exit(1)

    print(f"Using API ID: {settings.telegram_api_id}")
    print(f"Session will be saved to: {_SESSION_PATH}.session")
    print()

    client = TelegramClient(_SESSION_PATH, settings.telegram_api_id, settings.telegram_api_hash)
    await client.start()  # interactive: asks for phone + code + 2FA if needed

    me = await client.get_me()
    print(f"\n✓ Logged in as: {me.first_name} (@{me.username or 'no username'})")
    print("✓ Session saved. Telegram ingestion is now active.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
