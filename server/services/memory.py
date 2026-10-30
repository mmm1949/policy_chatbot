import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator


class ConversationMemory:
    def __init__(
        self,
        database_path: Path,
        max_conversations: int = 256,
        max_messages: int = 12,
        max_exchanges: int = 200,
    ) -> None:
        if (
            max_conversations < 1
            or max_messages < 2
            or max_messages % 2
            or max_exchanges < max_messages // 2
        ):
            raise ValueError("Memory limits must allow at least one conversation and an even number of messages.")
        self.database_path = database_path
        self.max_conversations = max_conversations
        self.max_messages = max_messages
        self.max_exchanges = max_exchanges
        self._lock = RLock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_exchanges_conversation
                ON conversation_exchanges (conversation_id, id DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_activity (
                    conversation_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, conversation_id: str) -> list[dict[str, str]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT question, answer
                FROM conversation_exchanges
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, self.max_messages // 2),
            ).fetchall()
        messages = []
        for question, answer in reversed(rows):
            messages.extend((
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ))
        return messages

    def recall(
        self,
        conversation_id: str,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, str]]:
        recent_count = self.max_messages // 2
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT question, answer
                FROM conversation_exchanges
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (conversation_id, self.max_exchanges, recent_count),
            ).fetchall()
        query_terms = self._terms(query)
        if not query_terms:
            return []
        ranked = []
        for position, (question, answer) in enumerate(rows):
            terms = self._terms(f"{question} {answer}")
            score = len(query_terms & terms)
            if score:
                ranked.append((score, position, question, answer))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        recalled = []
        for _, _, question, answer in ranked[:limit]:
            recalled.extend((
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ))
        return recalled

    def add_exchange(self, conversation_id: str, question: str, answer: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_exchanges (conversation_id, question, answer)
                VALUES (?, ?, ?)
                """,
                (conversation_id, question, answer),
            )
            connection.execute(
                """
                INSERT INTO conversation_activity (conversation_id, updated_at)
                VALUES (?, STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))
                ON CONFLICT(conversation_id)
                DO UPDATE SET updated_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW')
                """,
                (conversation_id,),
            )
            connection.execute(
                """
                DELETE FROM conversation_exchanges
                WHERE conversation_id = ?
                  AND id NOT IN (
                      SELECT id FROM conversation_exchanges
                      WHERE conversation_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (conversation_id, conversation_id, self.max_exchanges),
            )
            connection.execute(
                """
                DELETE FROM conversation_activity
                WHERE conversation_id NOT IN (
                    SELECT conversation_id FROM conversation_activity
                    ORDER BY updated_at DESC
                    LIMIT ?
                )
                """,
                (self.max_conversations,),
            )
            connection.execute(
                """
                DELETE FROM conversation_exchanges
                WHERE conversation_id NOT IN (
                    SELECT conversation_id FROM conversation_activity
                )
                """
            )

    def clear(self, conversation_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM conversation_exchanges WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM conversation_activity WHERE conversation_id = ?",
                (conversation_id,),
            )

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            term.casefold()
            for term in re.findall(r"\b[\w'-]{3,}\b", text)
        }
