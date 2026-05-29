"""SQLite-backed message store. Survives restarts when DB lives on a Railway volume."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredMessage:
    chat_id: int
    user_id: int
    message_id: int
    date: int  # unix timestamp
    username: str | None
    display_name: str
    text: str


@dataclass
class MediaItem:
    chat_id: int
    user_id: int
    message_id: int
    date: int  # unix timestamp
    username: str | None
    display_name: str
    kind: str  # 'sticker', 'gif', 'video', 'document', 'photo', ...
    file_id: str
    file_unique_id: str
    file_name: str | None


class MessageStore:
    def __init__(self, path: str | Path = "naserbot.db") -> None:
        self.path = str(path)
        # Make sure parent dir exists (matters when path is /data/naserbot.db on Railway).
        parent = Path(self.path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    chat_id      INTEGER NOT NULL,
                    message_id   INTEGER NOT NULL,
                    user_id      INTEGER NOT NULL,
                    date         INTEGER NOT NULL,
                    username     TEXT,
                    display_name TEXT NOT NULL,
                    text         TEXT NOT NULL,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_chat_user "
                "ON messages(chat_id, user_id, message_id)"
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS media (
                    chat_id        INTEGER NOT NULL,
                    message_id     INTEGER NOT NULL,
                    user_id        INTEGER NOT NULL,
                    date           INTEGER NOT NULL,
                    username       TEXT,
                    display_name   TEXT NOT NULL,
                    kind           TEXT NOT NULL,
                    file_id        TEXT NOT NULL,
                    file_unique_id TEXT NOT NULL,
                    file_name      TEXT,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_chat_user_kind "
                "ON media(chat_id, user_id, kind, message_id)"
            )

    def save(self, msg: StoredMessage) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO messages
                    (chat_id, message_id, user_id, date, username, display_name, text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.chat_id,
                    msg.message_id,
                    msg.user_id,
                    msg.date,
                    msg.username,
                    msg.display_name,
                    msg.text,
                ),
            )

    def save_media(self, item: MediaItem) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO media
                    (chat_id, message_id, user_id, date, username, display_name,
                     kind, file_id, file_unique_id, file_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.chat_id,
                    item.message_id,
                    item.user_id,
                    item.date,
                    item.username,
                    item.display_name,
                    item.kind,
                    item.file_id,
                    item.file_unique_id,
                    item.file_name,
                ),
            )

    def recent_media(
        self,
        chat_id: int | None = None,
        user_id: int | None = None,
        display_name: str | None = None,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[MediaItem]:
        """Most-recent-first media, optionally filtered by chat/user/name/kind."""
        clauses, params = [], []
        if chat_id is not None:
            clauses.append("chat_id = ?")
            params.append(chat_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if display_name is not None:
            clauses.append("display_name = ?")
            params.append(display_name)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._conn() as c:
            rows = c.execute(
                f"""
                SELECT chat_id, user_id, message_id, date, username, display_name,
                       kind, file_id, file_unique_id, file_name
                FROM media
                {where}
                ORDER BY message_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            MediaItem(
                chat_id=r[0],
                user_id=r[1],
                message_id=r[2],
                date=r[3],
                username=r[4],
                display_name=r[5],
                kind=r[6],
                file_id=r[7],
                file_unique_id=r[8],
                file_name=r[9],
            )
            for r in rows
        ]

    def last_message_id_from_user(
        self, chat_id: int, user_id: int, before_message_id: int
    ) -> int | None:
        """The largest message_id from this user in this chat, strictly before `before_message_id`."""
        with self._conn() as c:
            row = c.execute(
                """
                SELECT MAX(message_id) FROM messages
                WHERE chat_id = ? AND user_id = ? AND message_id < ?
                """,
                (chat_id, user_id, before_message_id),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def stats(self) -> dict:
        """Quick health snapshot of what's actually persisted."""
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            chats = c.execute("SELECT COUNT(DISTINCT chat_id) FROM messages").fetchone()[0]
            users = c.execute("SELECT COUNT(DISTINCT user_id) FROM messages").fetchone()[0]
            extremes = c.execute(
                "SELECT MIN(date), MAX(date), MIN(message_id), MAX(message_id) FROM messages"
            ).fetchone()
            per_chat = c.execute(
                "SELECT chat_id, COUNT(*), MIN(message_id), MAX(message_id) "
                "FROM messages GROUP BY chat_id ORDER BY 2 DESC LIMIT 5"
            ).fetchall()
        return {
            "total": total,
            "chats": chats,
            "users": users,
            "min_date": extremes[0],
            "max_date": extremes[1],
            "min_msg_id": extremes[2],
            "max_msg_id": extremes[3],
            "top_chats": per_chat,
        }

    def messages_in_range(
        self, chat_id: int, after_message_id: int, before_message_id: int
    ) -> list[StoredMessage]:
        """Messages with after_message_id < message_id < before_message_id, ordered."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT chat_id, user_id, message_id, date, username, display_name, text
                FROM messages
                WHERE chat_id = ? AND message_id > ? AND message_id < ?
                ORDER BY message_id ASC
                """,
                (chat_id, after_message_id, before_message_id),
            ).fetchall()
        return [
            StoredMessage(
                chat_id=r[0],
                user_id=r[1],
                message_id=r[2],
                date=r[3],
                username=r[4],
                display_name=r[5],
                text=r[6],
            )
            for r in rows
        ]
