import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from llm import summarize_conversation
from store import MessageStore, StoredMessage

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_CHAT_ID = int(os.environ["OWNER_CHAT_ID"])

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("naserbot")

store = MessageStore()


def _display_name(user) -> str:
    if user is None:
        return "unknown"
    name = (user.first_name or "").strip()
    if user.last_name:
        name = f"{name} {user.last_name}".strip()
    return name or (user.username or f"id{user.id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Naser is alive. Use /summary in a group to catch up.")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")


async def record_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if msg is None or msg.text is None:
        return
    user = msg.from_user
    if user is None or user.is_bot:
        return
    store.save(
        StoredMessage(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            user_id=user.id,
            date=int(msg.date.timestamp()),
            username=user.username,
            display_name=_display_name(user),
            text=msg.text,
        )
    )


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if msg is None or msg.from_user is None:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("This command only makes sense in a group.")
        return

    user = msg.from_user
    last_id = store.last_message_id_from_user(chat.id, user.id, msg.message_id)

    if last_id is None:
        await msg.reply_text(
            "I don't have any previous message from you in this chat yet. "
            "Send something, then try /summary later to catch up on what you missed."
        )
        return

    rows = store.messages_in_range(chat.id, last_id, msg.message_id)
    if not rows:
        await msg.reply_text("Nothing new since your last message.")
        return

    transcript = "\n".join(f"{r.display_name}: {r.text}" for r in rows)
    logger.info(
        "Summary requested by %s in chat %s — %d messages",
        user.id,
        chat.id,
        len(rows),
    )

    await context.bot.send_chat_action(chat.id, ChatAction.TYPING)
    try:
        result = await summarize_conversation(transcript)
    except Exception:
        logger.exception("LLM call failed")
        await msg.reply_text("Sorry, summary failed. Try again in a sec.")
        return

    header = f"📝 Summary since your last message ({len(rows)} msgs):\n\n"
    await msg.reply_text(header + result)


async def on_startup(app: Application) -> None:
    await app.bot.send_message(chat_id=OWNER_CHAT_ID, text="✅ NaserBot is online.")
    logger.info("Sent startup message to %s", OWNER_CHAT_ID)


def main() -> None:
    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("summary", summary))
    # Record every plain text message (groups + private), excluding commands.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, record_message))

    logger.info("Starting NaserBot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
