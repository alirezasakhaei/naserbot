"""Tiny SQLite layer for storing group messages."""
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


class MessageStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
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
                "CREATE INDEX IF NOT EXISTS idx_messages_chat_user ON messages(chat_id, user_id, message_id)"
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

    def last_message_id_from_user(
        self, chat_id: int, user_id: int, before_message_id: int
    ) -> int | None:
        """The largest message_id in this chat from this user, strictly before `before_message_id`."""
        with self._conn() as c:
            row = c.execute(
                """
                SELECT MAX(message_id) FROM messages
                WHERE chat_id = ? AND user_id = ? AND message_id < ?
                """,
                (chat_id, user_id, before_message_id),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def messages_in_range(
        self, chat_id: int, after_message_id: int, before_message_id: int
    ) -> list[StoredMessage]:
        """Messages in (after_message_id, before_message_id), exclusive on both ends."""
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
