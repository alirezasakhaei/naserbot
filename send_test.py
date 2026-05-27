"""One-shot test: send a message to OWNER_CHAT_ID and exit."""
import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot

load_dotenv()


async def main() -> None:
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    chat_id = int(os.environ["OWNER_CHAT_ID"])
    msg = await bot.send_message(chat_id=chat_id, text="👋 Hello from NaserBot — setup works.")
    print(f"Sent message {msg.message_id} to chat {chat_id}")


if __name__ == "__main__":
    asyncio.run(main())
