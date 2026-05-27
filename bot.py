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
DB_PATH = os.environ.get("NASERBOT_DB", "naserbot.db")

# Sticker auto-reply: when a sticker with file_unique_id == TRIGGER fires,
# reply with the sticker whose file_id == RESPONSE. Both optional.
STICKER_TRIGGER_UNIQUE_ID = os.environ.get("STICKER_TRIGGER_UNIQUE_ID", "").strip()
STICKER_RESPONSE_FILE_ID = os.environ.get("STICKER_RESPONSE_FILE_ID", "").strip()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("naserbot")

store = MessageStore(DB_PATH)
logger.info("Message store at %s", DB_PATH)


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
    logger.info(
        "saved msg chat=%s user=%s(%s) id=%s text=%r",
        msg.chat_id,
        _display_name(user),
        user.id,
        msg.message_id,
        msg.text[:60],
    )


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if msg is None or msg.sticker is None:
        return
    s = msg.sticker
    logger.info(
        "STICKER chat=%s from=%s file_id=%s file_unique_id=%s emoji=%s set=%s",
        msg.chat_id,
        msg.from_user.id if msg.from_user else None,
        s.file_id,
        s.file_unique_id,
        s.emoji,
        s.set_name,
    )
    if (
        STICKER_TRIGGER_UNIQUE_ID
        and STICKER_RESPONSE_FILE_ID
        and s.file_unique_id == STICKER_TRIGGER_UNIQUE_ID
    ):
        try:
            await msg.reply_sticker(STICKER_RESPONSE_FILE_ID)
            logger.info("Sent auto-reply sticker in chat %s", msg.chat_id)
        except Exception:
            logger.exception("Failed to send auto-reply sticker")


async def debug_any(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs every update so we can see what Telegram is actually delivering."""
    msg = update.message or update.edited_message
    if msg is None:
        logger.info("update without message: %s", update.to_dict())
        return
    logger.info(
        "RAW update chat=%s type=%s from=%s has_text=%s",
        msg.chat_id,
        msg.chat.type,
        msg.from_user.id if msg.from_user else None,
        bool(msg.text),
    )


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if msg is None or msg.from_user is None:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("این دستور فقط داخل گروه کار می‌کنه.")
        return

    user = msg.from_user
    last_id = store.last_message_id_from_user(chat.id, user.id, msg.message_id)

    if last_id is None:
        await msg.reply_text(
            "هنوز هیچ پیامی ازت توی این گروه ندارم. "
            "یه پیام بفرست، بعداً با /summary بگو چه چیزایی رو از دست دادی."
        )
        return

    rows = store.messages_in_range(chat.id, last_id, msg.message_id)
    if not rows:
        await msg.reply_text("از آخرین پیامت چیز جدیدی نبوده.")
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
        await msg.reply_text("ببخشید، خلاصه نشد. یه لحظه دیگه دوباره امتحان کن.")
        return

    header = f"📝 خلاصه از آخرین پیامت تا الان ({len(rows)} پیام):\n\n"
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
    # Sticker auto-reply + sticker ID logger.
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    # Debug: log EVERY incoming update so we can diagnose privacy/delivery issues.
    app.add_handler(MessageHandler(filters.ALL, debug_any), group=1)

    logger.info("Starting NaserBot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
