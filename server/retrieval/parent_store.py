import json
import sqlite3
from pathlib import Path

from langchain_core.documents import Document


class ParentDocumentStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS parent_documents (
                    parent_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )

    @property
    def count(self) -> int:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM parent_documents"
            ).fetchone()
        return int(row[0])

    def replace(self, documents: list[Document]) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM parent_documents")
            connection.executemany(
                """
                INSERT INTO parent_documents (parent_id, content, metadata)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        str(document.metadata["parent_id"]),
                        document.page_content,
                        json.dumps(document.metadata),
                    )
                    for document in documents
                ],
            )

    def get_many(self, parent_ids: list[str]) -> dict[str, Document]:
        if not parent_ids:
            return {}
        placeholders = ",".join("?" for _ in parent_ids)
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT parent_id, content, metadata
                FROM parent_documents
                WHERE parent_id IN ({placeholders})
                """,
                parent_ids,
            ).fetchall()
        return {
            parent_id: Document(page_content=content, metadata=json.loads(metadata))
            for parent_id, content, metadata in rows
        }
