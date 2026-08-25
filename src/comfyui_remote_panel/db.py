from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "interrupted", "output_missing"}
ACTIVE_STATUSES = {"submitting", "queued", "running"}
HIDDEN_STATUS = "hidden"


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            with self._connect() as db:
                db.execute("PRAGMA journal_mode = WAL")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    db.executescript(
                        """
                        CREATE TABLE jobs (
                            id TEXT PRIMARY KEY,
                            preset_id TEXT NOT NULL,
                            status TEXT NOT NULL,
                            mode TEXT NOT NULL,
                            prompt TEXT NOT NULL,
                            duration_seconds INTEGER NOT NULL,
                            aspect_ratio TEXT NOT NULL,
                            megapixels REAL NOT NULL,
                            seed TEXT NOT NULL,
                            scheduler TEXT NOT NULL,
                            sampler TEXT NOT NULL,
                            steps INTEGER NOT NULL,
                            queue_position INTEGER,
                            stage TEXT,
                            progress_value INTEGER,
                            progress_max INTEGER,
                            error_code TEXT,
                            error_summary TEXT,
                            created_at REAL NOT NULL,
                            started_at REAL,
                            finished_at REAL,
                            recovery_attempts INTEGER NOT NULL DEFAULT 0,
                            recovery_next_at REAL,
                            recovery_last_error TEXT,
                            cancel_requested_at REAL,
                            missing_observations INTEGER NOT NULL DEFAULT 0,
                            missing_first_at REAL,
                            updated_at REAL NOT NULL
                        );
                        CREATE INDEX jobs_created_at_idx ON jobs(created_at DESC);
                        CREATE INDEX jobs_status_idx ON jobs(status);
                        CREATE TABLE job_files (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                            role TEXT NOT NULL,
                            path TEXT NOT NULL UNIQUE,
                            size_bytes INTEGER NOT NULL,
                            UNIQUE(job_id, role)
                        );
                        PRAGMA user_version = 4;
                        """
                    )
                    version = 4
                if version == 1:
                    db.executescript(
                        """
                        ALTER TABLE jobs ADD COLUMN scheduler TEXT NOT NULL DEFAULT 'beta';
                        ALTER TABLE jobs ADD COLUMN sampler TEXT NOT NULL DEFAULT 'euler';
                        ALTER TABLE jobs ADD COLUMN steps INTEGER NOT NULL DEFAULT 8;
                        PRAGMA user_version = 2;
                        """
                    )
                    version = 2
                if version == 2:
                    db.executescript(
                        """
                        ALTER TABLE jobs ADD COLUMN recovery_attempts INTEGER NOT NULL DEFAULT 0;
                        ALTER TABLE jobs ADD COLUMN recovery_next_at REAL;
                        ALTER TABLE jobs ADD COLUMN recovery_last_error TEXT;
                        PRAGMA user_version = 3;
                        """
                    )
                    version = 3
                if version == 3:
                    db.executescript(
                        """
                        ALTER TABLE jobs ADD COLUMN cancel_requested_at REAL;
                        ALTER TABLE jobs ADD COLUMN missing_observations INTEGER NOT NULL DEFAULT 0;
                        ALTER TABLE jobs ADD COLUMN missing_first_at REAL;
                        PRAGMA user_version = 4;
                        """
                    )
                    version = 4
                if version != 4:
                    raise RuntimeError(f"unsupported database schema version: {version}")

    async def create_job(self, record: dict[str, Any], files: list[dict[str, Any]]) -> None:
        now = time.time()
        async with self._lock:
            with self._connect() as db:
                db.execute(
                    """INSERT INTO jobs (
                        id, preset_id, status, mode, prompt, duration_seconds,
                        aspect_ratio, megapixels, seed, scheduler, sampler, steps,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record["id"], record["preset_id"], record["status"], record["mode"],
                        record["prompt"], record["duration_seconds"], record["aspect_ratio"],
                        record["megapixels"], str(record["seed"]), record.get("scheduler", "beta"),
                        record.get("sampler", "euler"), record.get("steps", 8), now, now,
                    ),
                )
                for file in files:
                    db.execute(
                        "INSERT INTO job_files(job_id, role, path, size_bytes) VALUES (?, ?, ?, ?)",
                        (record["id"], file["role"], str(file["path"]), file["size_bytes"]),
                    )

    async def update_job(self, job_id: str, **values: Any) -> dict[str, Any] | None:
        allowed = {
            "status", "queue_position", "stage", "progress_value", "progress_max",
            "error_code", "error_summary", "started_at", "finished_at",
            "recovery_attempts", "recovery_next_at", "recovery_last_error",
            "cancel_requested_at", "missing_observations", "missing_first_at",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported job fields: {sorted(unknown)}")
        values["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in values)
        async with self._lock:
            with self._connect() as db:
                db.execute(
                    f"UPDATE jobs SET {assignments} WHERE id = ?",
                    (*values.values(), job_id),
                )
        return await self.get_job(job_id)

    async def update_active_job(self, job_id: str, **values: Any) -> dict[str, Any] | None:
        _, job = await self.update_job_if_status(job_id, ACTIVE_STATUSES, **values)
        return job

    async def update_job_if_status(
        self, job_id: str, expected: set[str], **values: Any
    ) -> tuple[bool, dict[str, Any] | None]:
        allowed = {
            "status", "queue_position", "stage", "progress_value", "progress_max",
            "error_code", "error_summary", "started_at", "finished_at",
            "recovery_attempts", "recovery_next_at", "recovery_last_error",
            "cancel_requested_at", "missing_observations", "missing_first_at",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported job fields: {sorted(unknown)}")
        values["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in values)
        statuses = sorted(expected)
        if not statuses:
            raise ValueError("expected statuses must not be empty")
        placeholders = ",".join("?" for _ in statuses)
        async with self._lock:
            with self._connect() as db:
                cursor = db.execute(
                    f"UPDATE jobs SET {assignments} WHERE id = ? AND status IN ({placeholders})",
                    (*values.values(), job_id, *statuses),
                )
                updated = cursor.rowcount == 1
        return updated, await self.get_job(job_id)

    async def add_file(self, job_id: str, role: str, path: Path, size_bytes: int) -> None:
        async with self._lock:
            with self._connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO job_files(job_id, role, path, size_bytes) VALUES (?, ?, ?, ?)",
                    (job_id, role, str(path), size_bytes),
                )

    def _job_from_row(self, row: sqlite3.Row, files: list[dict[str, Any]]) -> dict[str, Any]:
        item = dict(row)
        item["files"] = files
        item["size_bytes"] = sum(f["size_bytes"] for f in files)
        value, maximum = item.get("progress_value"), item.get("progress_max")
        item["progress_percent"] = round(value * 100 / maximum) if value is not None and maximum else None
        item["has_video"] = any(f["role"] == "output" for f in files)
        now = item.get("finished_at") or time.time()
        start = item.get("started_at") or item["created_at"]
        item["elapsed_seconds"] = max(0, round(now - start))
        return item

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        async with self._lock:
            with self._connect() as db:
                row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None:
                    return None
                files = [dict(v) for v in db.execute("SELECT role, path, size_bytes FROM job_files WHERE job_id = ? ORDER BY id", (job_id,))]
        return self._job_from_row(row, files)

    async def list_jobs(self, page: int = 1, page_size: int = 20, statuses: set[str] | None = None) -> dict[str, Any]:
        conditions = ["status != ?"]
        params: list[Any] = [HIDDEN_STATUS]
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(sorted(statuses))
        where = " WHERE " + " AND ".join(conditions)
        async with self._lock:
            with self._connect() as db:
                total = db.execute(f"SELECT COUNT(*) FROM jobs{where}", params).fetchone()[0]
                rows = db.execute(
                    f"SELECT * FROM jobs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (*params, page_size, (page - 1) * page_size),
                ).fetchall()
                job_ids = [row["id"] for row in rows]
                files_by_job: dict[str, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
                if job_ids:
                    marks = ",".join("?" for _ in job_ids)
                    for file in db.execute(f"SELECT job_id, role, path, size_bytes FROM job_files WHERE job_id IN ({marks}) ORDER BY id", job_ids):
                        files_by_job[file["job_id"]].append({key: file[key] for key in ("role", "path", "size_bytes")})
        return {
            "items": [self._job_from_row(row, files_by_job[row["id"]]) for row in rows],
            "pagination": {"page": page, "page_size": page_size, "total": total, "has_more": page * page_size < total},
        }

    async def active_jobs(self) -> list[dict[str, Any]]:
        statuses = sorted(ACTIVE_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        async with self._lock:
            with self._connect() as db:
                rows = db.execute(
                    f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at",
                    statuses,
                ).fetchall()
                job_ids = [row["id"] for row in rows]
                files_by_job: dict[str, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
                if job_ids:
                    marks = ",".join("?" for _ in job_ids)
                    for file in db.execute(
                        f"SELECT job_id, role, path, size_bytes FROM job_files WHERE job_id IN ({marks}) ORDER BY id",
                        job_ids,
                    ):
                        files_by_job[file["job_id"]].append(
                            {key: file[key] for key in ("role", "path", "size_bytes")}
                        )
        return [self._job_from_row(row, files_by_job[row["id"]]) for row in rows]

    async def succeeded_without_output(self, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        async with self._lock:
            return await asyncio.to_thread(self._succeeded_without_output, now)

    def _succeeded_without_output(self, now: float) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM jobs
                   WHERE status = 'succeeded'
                     AND COALESCE(recovery_next_at, 0) <= ?
                     AND NOT EXISTS (
                       SELECT 1 FROM job_files
                       WHERE job_files.job_id = jobs.id AND job_files.role = 'output'
                     )
                   ORDER BY finished_at DESC""",
                (now,),
            ).fetchall()
            return [self._job_from_row(row, []) for row in rows]

    async def delete_job(self, job_id: str) -> None:
        async with self._lock:
            with self._connect() as db:
                db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    async def tracked_size(self) -> int:
        async with self._lock:
            with self._connect() as db:
                return int(db.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM job_files").fetchone()[0])

    async def tracked_paths(self) -> set[Path]:
        async with self._lock:
            with self._connect() as db:
                return {Path(row[0]) for row in db.execute("SELECT path FROM job_files")}

    async def tracked_files(self) -> list[dict[str, Any]]:
        async with self._lock:
            with self._connect() as db:
                return [
                    {"job_id": row[0], "role": row[1], "path": row[2], "size_bytes": row[3], "status": row[4]}
                    for row in db.execute(
                        "SELECT job_files.job_id, job_files.role, job_files.path, job_files.size_bytes, jobs.status "
                        "FROM job_files JOIN jobs ON jobs.id = job_files.job_id ORDER BY job_files.id"
                    )
                ]

    async def update_file_path(self, job_id: str, role: str, path: Path, size_bytes: int) -> None:
        async with self._lock:
            with self._connect() as db:
                db.execute(
                    "UPDATE job_files SET path = ?, size_bytes = ? WHERE job_id = ? AND role = ?",
                    (str(path), size_bytes, job_id, role),
                )
