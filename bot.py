# NaserBot — Telegram group bot with /summary
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
from store import MediaItem, MessageStore, StoredMessage

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_CHAT_ID = int(os.environ["OWNER_CHAT_ID"])
DB_PATH = os.environ.get("NASERBOT_DB", "naserbot.db")

# --- Media auto-reply file_ids ---------------------------------------------
# Heli's media (file_ids captured from logs).
_HELI_GIF1 = "CgACAgQAAyEFAATpJtHYAAIyFmoXcWiIZyS0HZ-zD3pwtBv-hFJmAALMBwACf9pAUApjX3a9mdj6OwQ"
_HELI_GIF2 = "CgACAgQAAyEFAATpJtHYAAIzWGoYaPQGllyLgseLXm6r9K_dc1dfAAJLBgACPBgQU7y2Ily1U-IROwQ"
_HELI_GIF3 = "CgACAgEAAyEFAATpJtHYAAIzV2oYZ3yaex6oZgPKJDnKgEqmuR6oAAI_AQACGK0BR_G3Q3UfxOvaOwQ"
_HELI_STICKER = "CAACAgQAAyEFAATpJtHYAAI1QGoaG419OWedNmWsGbx4GHw5dWp_AAICHgAC6dWhUlGotUjHfsZZOwQ"
_OLD_STICKER = "CAACAgQAAxkBAAJCkWoXZmEUi_wXpCeCI6KGNdJ121PHAAJzHAACtHWxUjOrC3r7CNjgOwQ"
# Correct sticker for the GIF#1 two-way pair.
_PAIR_STICKER = "CAACAgQAAyEFAATpJtHYAAIyDGoXcTyIeKGbgf54vvsNaqnbPhumAAKtIQAC2UbhU1EQMwxpL77lOwQ"

# Auto-reply map. Key = incoming media's file_unique_id.
# Value = (how to send the reply, file_id to send). "gif" -> reply_animation,
# "sticker" -> reply_sticker. Pairs that point at each other = two-way trigger.
MEDIA_REPLIES: dict[str, tuple[str, str]] = {
    # Heli's two latest GIFs trigger each other.
    "AgADSwYAAjwYEFM": ("gif", _HELI_GIF3),  # GIF#2 -> GIF#3
    "AgADPwEAAhitAUc": ("gif", _HELI_GIF2),  # GIF#3 -> GIF#2
    # Current sticker -> previous trigger sticker (one-way).
    "AgADAh4AAunVoVI": ("sticker", _OLD_STICKER),
    # Original 🫥 sticker keeps its one-way reply.
    "AgADgBsAAoWhoVI": ("sticker", _OLD_STICKER),
    # Heli's first GIF <-> the correct pair sticker (two-way).
    "AgADzAcAAn_aQFA": ("sticker", _PAIR_STICKER),  # GIF#1   -> pair sticker
    "AgADrSEAAtlG4VM": ("gif", _HELI_GIF1),          # sticker -> GIF#1
    # Aryan's GIF -> credit text (one-way).
    "AgADByAAAihX2VA": ("text", "©️ @AryanAhadinia"),
    # Heli's sticker -> credit text (one-way).
    "AgAD1BIAAhE0YVA": ("text", "©️@lilyorheli"),
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("naserbot")
# Silence the constant "POST .../getUpdates 200 OK" polling spam.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)

# --- Volume audit: prove (or disprove) that /data is actually persistent ---
from pathlib import Path as _P  # noqa: E402
import datetime as _dt  # noqa: E402

_db_dir = _P(DB_PATH).parent
_marker = _db_dir / "boot_marker.txt"
try:
    _db_dir.mkdir(parents=True, exist_ok=True)
    _existed = _marker.exists()
    _prev = _marker.read_text().strip() if _existed else "(none)"
    _now = _dt.datetime.utcnow().isoformat() + "Z"
    _marker.write_text(_now)
    logger.info("VOLUME AUDIT: dir=%s exists=%s prev_marker=%s new_marker=%s",
                _db_dir, _existed, _prev, _now)
    try:
        _ls = sorted(p.name + (f" ({p.stat().st_size}B)" if p.is_file() else "/") for p in _db_dir.iterdir())
        logger.info("VOLUME AUDIT: contents of %s = %s", _db_dir, _ls)
    except Exception as e:
        logger.warning("VOLUME AUDIT: ls failed: %s", e)
except Exception:
    logger.exception("VOLUME AUDIT failed")

store = MessageStore(DB_PATH)
logger.info("Message store at %s", DB_PATH)
_stats = store.stats()
logger.info(
    "DB on startup: %d msgs / %d chats / %d users / msg_id range [%s..%s] / date range [%s..%s]",
    _stats["total"],
    _stats["chats"],
    _stats["users"],
    _stats["min_msg_id"],
    _stats["max_msg_id"],
    _stats["min_date"],
    _stats["max_date"],
)
for chat_id, n, mn, mx in _stats["top_chats"]:
    logger.info("  chat %s: %d msgs, ids %s..%s", chat_id, n, mn, mx)


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


def _extract_media(msg):
    """Return (kind, media_obj) for the first media attribute present, else (None, None).

    'animation' is normalised to kind='gif'. Photos return their largest size.
    """
    for attr in (
        "sticker",
        "animation",
        "video",
        "video_note",
        "document",
        "photo",
        "audio",
        "voice",
    ):
        val = getattr(msg, attr, None)
        if val:
            if attr == "photo":
                val = val[-1]  # largest PhotoSize
            kind = "gif" if attr == "animation" else attr
            return kind, val
    return None, None


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persist any media to the DB and fire auto-replies on configured triggers."""
    msg = update.message
    if msg is None:
        return
    kind, media = _extract_media(msg)
    if media is None:
        return
    user = msg.from_user

    if user is not None and not user.is_bot:
        store.save_media(
            MediaItem(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                user_id=user.id,
                date=int(msg.date.timestamp()),
                username=user.username,
                display_name=_display_name(user),
                kind=kind,
                file_id=media.file_id,
                file_unique_id=media.file_unique_id,
                file_name=getattr(media, "file_name", None),
            )
        )
    logger.info(
        "MEDIA kind=%s from=%s file_unique_id=%s",
        kind,
        user.id if user else None,
        media.file_unique_id,
    )

    reply = MEDIA_REPLIES.get(media.file_unique_id)
    if reply:
        reply_kind, reply_payload = reply
        try:
            if reply_kind == "sticker":
                await msg.reply_sticker(reply_payload)
            elif reply_kind == "text":
                await msg.reply_text(reply_payload)
            else:
                await msg.reply_animation(reply_payload)
            logger.info(
                "Auto-replied %s to trigger %s in chat %s",
                reply_kind,
                media.file_unique_id,
                msg.chat_id,
            )
        except Exception:
            logger.exception("Failed to send auto-reply media")


def _content_kind(msg) -> str:
    """Best-effort label of what kind of content a non-text message carries."""
    for attr in (
        "text",
        "sticker",
        "animation",
        "video",
        "video_note",
        "photo",
        "document",
        "audio",
        "voice",
        "poll",
        "dice",
        "location",
        "contact",
    ):
        val = getattr(msg, attr, None)
        if val:
            return attr
    return "unknown"


async def debug_any(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs every update so we can see what Telegram is actually delivering."""
    msg = update.message or update.edited_message
    if msg is None:
        logger.info("update without message: %s", update.to_dict())
        return
    kind = _content_kind(msg)
    # Surface the file_id/unique_id for any media so nothing slips through silently.
    media = getattr(msg, kind, None) if kind not in ("text", "unknown") else None
    file_id = getattr(media, "file_id", None)
    file_unique_id = getattr(media, "file_unique_id", None)
    file_name = getattr(media, "file_name", None)
    logger.info(
        "RAW chat=%s from=%s kind=%s file_id=%s file_unique_id=%s name=%s",
        msg.chat_id,
        msg.from_user.id if msg.from_user else None,
        kind,
        file_id,
        file_unique_id,
        file_name,
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

    # If the command is a reply, summarize from the replied-to message to the end.
    if msg.reply_to_message is not None:
        # Exclusive lower bound -> include the replied-to message itself.
        after_id = msg.reply_to_message.message_id - 1
        rows = store.messages_in_range(chat.id, after_id, msg.message_id)
        if not rows:
            await msg.reply_text("از اون پیام به بعد چیزی برای خلاصه کردن نیست.")
            return
    else:
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
        result = await summarize_conversation(transcript, requester_name=_display_name(user))
    except Exception:
        logger.exception("LLM call failed")
        await msg.reply_text("ببخشید، خلاصه نشد. یه لحظه دیگه دوباره امتحان کن.")
        return

    await msg.reply_text(result)


async def on_startup(app: Application) -> None:
    await app.bot.send_message(chat_id=OWNER_CHAT_ID, text="✅ NaserBot is online.")
    logger.info("Sent startup message to %s", OWNER_CHAT_ID)


def main() -> None:
    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler(["summary", "sum", "s"], summary))
    # Record every plain text message (groups + private), excluding commands.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, record_message))
    # Persist + auto-reply for all media (stickers, GIFs, video, docs, photos...).
    app.add_handler(
        MessageHandler(
            filters.Sticker.ALL
            | filters.ANIMATION
            | filters.VIDEO
            | filters.VIDEO_NOTE
            | filters.Document.ALL
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE,
            handle_media,
        )
    )
    # Debug: log EVERY incoming update so we can diagnose privacy/delivery issues.
    app.add_handler(MessageHandler(filters.ALL, debug_any), group=1)

    logger.info("Starting NaserBot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
