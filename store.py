"""In-memory message store. Lost on restart — fine for now."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

MAX_PER_CHAT = 2000  # ring-buffer cap per chat


@dataclass
class StoredMessage:
    chat_id: int
    user_id: int
    message_id: int
    date: int
    username: str | None
    display_name: str
    text: str


class MessageStore:
    def __init__(self, max_per_chat: int = MAX_PER_CHAT) -> None:
        # chat_id -> deque[StoredMessage] ordered by message_id ascending
        self._by_chat: dict[int, deque[StoredMessage]] = defaultdict(
            lambda: deque(maxlen=max_per_chat)
        )

    def save(self, msg: StoredMessage) -> None:
        self._by_chat[msg.chat_id].append(msg)

    def last_message_id_from_user(
        self, chat_id: int, user_id: int, before_message_id: int
    ) -> int | None:
        last: int | None = None
        for m in self._by_chat.get(chat_id, ()):
            if m.user_id == user_id and m.message_id < before_message_id:
                if last is None or m.message_id > last:
                    last = m.message_id
        return last

    def messages_in_range(
        self, chat_id: int, after_message_id: int, before_message_id: int
    ) -> list[StoredMessage]:
        return [
            m
            for m in self._by_chat.get(chat_id, ())
            if after_message_id < m.message_id < before_message_id
        ]
