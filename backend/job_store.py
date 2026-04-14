import json
import sqlite3
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Tuple


class JobStore:
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
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)"
            )

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "payload": payload,
            "result": None,
            "error": None,
        }
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO jobs (job_id, status, created_at, updated_at, payload_json, result_json, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job["status"],
                        job["created_at"],
                        job["updated_at"],
                        json.dumps(payload),
                        None,
                        None,
                    ),
                )
        return job

    def _row_to_job(self, row: sqlite3.Row) -> Dict[str, Any]:
        result_json = row["result_json"]
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "payload": json.loads(row["payload_json"]),
            "result": json.loads(result_json) if result_json else None,
            "error": row["error"],
        }

    def get(self, job_id: str) -> Dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    def update(self, job_id: str, **updates: Any) -> Dict[str, Any] | None:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            job.update(updates)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()

            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = ?, updated_at = ?, payload_json = ?, result_json = ?, error = ?
                    WHERE job_id = ?
                    """,
                    (
                        job["status"],
                        job["updated_at"],
                        json.dumps(job.get("payload") or {}),
                        json.dumps(job["result"]) if job.get("result") is not None else None,
                        job.get("error"),
                        job_id,
                    ),
                )
        return job

    def list_recent(self, limit: int = 20, job_type: str | None = None) -> List[Dict[str, Any]]:
        jobs, _ = self.list_recent_paginated(limit=limit, job_type=job_type, cursor=None)
        return jobs

    def list_recent_paginated(
        self,
        limit: int = 20,
        job_type: str | None = None,
        cursor: str | None = None,
    ) -> Tuple[List[Dict[str, Any]], str | None]:
        safe_limit = min(max(limit, 1), 100)
        cursor_created_at = ""
        cursor_job_id = ""
        if cursor and "|" in cursor:
            cursor_created_at, cursor_job_id = cursor.split("|", 1)

        query = "SELECT * FROM jobs"
        params: List[Any] = []

        if cursor_created_at:
            query += " WHERE (created_at < ? OR (created_at = ? AND job_id < ?))"
            params.extend([cursor_created_at, cursor_created_at, cursor_job_id])

        query += " ORDER BY created_at DESC, job_id DESC LIMIT ?"
        params.append(safe_limit * 3)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        jobs = [self._row_to_job(row) for row in rows]
        if job_type:
            jobs = [job for job in jobs if job.get("payload", {}).get("job_type") == job_type]

        page = jobs[:safe_limit]
        next_cursor = None
        if len(jobs) > safe_limit and page:
            last = page[-1]
            next_cursor = f"{last.get('created_at', '')}|{last.get('job_id', '')}"

        return page, next_cursor

    def delete_older_than(self, cutoff_iso: str) -> int:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM jobs WHERE created_at < ?",
                    (cutoff_iso,),
                )
                return cursor.rowcount
