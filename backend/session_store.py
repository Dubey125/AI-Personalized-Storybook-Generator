import json
import sqlite3
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict


class SessionStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC)"
            )

    def get(self, session_id: str) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return {}
        return json.loads(row["metadata_json"])

    def upsert(self, session_id: str, metadata: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT session_id FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if existing:
                    connection.execute(
                        """
                        UPDATE sessions
                        SET metadata_json = ?, updated_at = ?
                        WHERE session_id = ?
                        """,
                        (json.dumps(metadata), now, session_id),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO sessions (session_id, metadata_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, json.dumps(metadata), now, now),
                    )

    def delete_older_than(self, cutoff_iso: str) -> int:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM sessions WHERE updated_at < ?",
                    (cutoff_iso,),
                )
                return cursor.rowcount
