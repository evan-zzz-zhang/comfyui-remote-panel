from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "interrupted", "output_missing"}
ACTIVE_STATUSES = {"submitting", "queued", "running"}
HIDDEN_STATUS = "hidden"


def _artifact_kind_for_role(role: str) -> str:
    if role == "output":
        return "video"
    for kind in ("image", "video", "audio"):
        if role.startswith(kind + "_"):
            return kind
    return "image" if role in {"first", "last"} else "file"


def _file_identity(path: str) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve(strict=False)))
    except OSError:
        return os.path.normcase(os.path.abspath(path))


def _deduplicate_file_sizes(rows: list[tuple[str, int]]) -> dict[str, tuple[Path, int]]:
    unique: dict[str, tuple[Path, int]] = {}
    for path, size_bytes in rows:
        key = _file_identity(path)
        size = max(0, int(size_bytes))
        previous = unique.get(key)
        if previous is None:
            unique[key] = (Path(path), size)
        else:
            unique[key] = (previous[0], max(previous[1], size))
    return unique


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
                            workflow_id TEXT,
                            workflow_revision INTEGER,
                            workflow_snapshot_json TEXT,
                            input_values_json TEXT,
                            is_test INTEGER NOT NULL DEFAULT 0,
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
                        CREATE TABLE workflows (
                            id TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            status TEXT NOT NULL,
                            name TEXT NOT NULL,
                            definition_json TEXT NOT NULL,
                            builtin INTEGER NOT NULL DEFAULT 0,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL,
                            PRIMARY KEY(id, revision)
                        );
                        CREATE INDEX workflows_status_idx ON workflows(status);
                        CREATE TABLE job_artifacts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                            direction TEXT NOT NULL,
                            binding_id TEXT NOT NULL,
                            ordinal INTEGER NOT NULL,
                            path TEXT NOT NULL UNIQUE,
                            kind TEXT NOT NULL,
                            mime_type TEXT,
                            original_name TEXT,
                            size_bytes INTEGER NOT NULL,
                            UNIQUE(job_id, direction, binding_id, ordinal)
                        );
                        PRAGMA user_version = 5;
                        """
                    )
                    version = 5
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
                if version == 4:
                    db.executescript(
                        """
                        ALTER TABLE jobs ADD COLUMN workflow_id TEXT;
                        ALTER TABLE jobs ADD COLUMN workflow_revision INTEGER;
                        ALTER TABLE jobs ADD COLUMN workflow_snapshot_json TEXT;
                        ALTER TABLE jobs ADD COLUMN input_values_json TEXT;
                        ALTER TABLE jobs ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0;
                        CREATE TABLE workflows (
                            id TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            status TEXT NOT NULL,
                            name TEXT NOT NULL,
                            definition_json TEXT NOT NULL,
                            builtin INTEGER NOT NULL DEFAULT 0,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL,
                            PRIMARY KEY(id, revision)
                        );
                        CREATE INDEX workflows_status_idx ON workflows(status);
                        CREATE TABLE job_artifacts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                            direction TEXT NOT NULL,
                            binding_id TEXT NOT NULL,
                            ordinal INTEGER NOT NULL,
                            path TEXT NOT NULL UNIQUE,
                            kind TEXT NOT NULL,
                            mime_type TEXT,
                            original_name TEXT,
                            size_bytes INTEGER NOT NULL,
                            UNIQUE(job_id, direction, binding_id, ordinal)
                        );
                        INSERT INTO job_artifacts(
                            job_id, direction, binding_id, ordinal, path, kind, size_bytes
                        )
                        SELECT job_id, CASE WHEN role = 'output' THEN 'output' ELSE 'input' END,
                               role, 0, path, CASE WHEN role = 'output' THEN 'video' ELSE 'file' END,
                               size_bytes
                        FROM job_files;
                        PRAGMA user_version = 5;
                        """
                    )
                    version = 5
                if version != 5:
                    raise RuntimeError(f"unsupported database schema version: {version}")

    async def create_job(self, record: dict[str, Any], files: list[dict[str, Any]]) -> None:
        now = time.time()
        async with self._lock:
            with self._connect() as db:
                db.execute(
                    """INSERT INTO jobs (
                        id, preset_id, status, mode, prompt, duration_seconds,
                        aspect_ratio, megapixels, seed, scheduler, sampler, steps,
                        workflow_id, workflow_revision, workflow_snapshot_json,
                        input_values_json, is_test, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record["id"], record["preset_id"], record["status"], record["mode"],
                        record.get("prompt", ""), record.get("duration_seconds", 0), record.get("aspect_ratio", "custom"),
                        record.get("megapixels", 0.0), str(record.get("seed", "0")), record.get("scheduler", "custom"),
                        record.get("sampler", "euler"), record.get("steps", 8),
                        record.get("workflow_id", record["preset_id"]), record.get("workflow_revision", 1),
                        json.dumps(record.get("workflow_snapshot"), ensure_ascii=False) if record.get("workflow_snapshot") else None,
                        json.dumps(record.get("input_values", {}), ensure_ascii=False),
                        int(bool(record.get("is_test"))), now, now,
                    ),
                )
                for file in files:
                    db.execute(
                        "INSERT INTO job_files(job_id, role, path, size_bytes) VALUES (?, ?, ?, ?)",
                        (record["id"], file["role"], str(file["path"]), file["size_bytes"]),
                    )
                    db.execute(
                        """INSERT OR IGNORE INTO job_artifacts(
                            job_id, direction, binding_id, ordinal, path, kind, size_bytes
                        ) VALUES (?, 'input', ?, 0, ?, ?, ?)""",
                        (record["id"], file["role"], str(file["path"]), _artifact_kind_for_role(file["role"]), file["size_bytes"]),
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
                db.execute(
                    """INSERT OR IGNORE INTO job_artifacts(
                        job_id, direction, binding_id, ordinal, path, kind, size_bytes
                    ) VALUES (?, ?, ?, 0, ?, ?, ?)""",
                    (job_id, "output" if role == "output" else "input", role, str(path), "video" if role == "output" else "file", size_bytes),
                )

    async def add_artifact(
        self, job_id: str, direction: str, binding_id: str, ordinal: int,
        path: Path, kind: str, mime_type: str | None, original_name: str | None,
        size_bytes: int,
    ) -> int:
        async with self._lock:
            with self._connect() as db:
                cursor = db.execute(
                    """INSERT OR REPLACE INTO job_artifacts(
                        job_id, direction, binding_id, ordinal, path, kind,
                        mime_type, original_name, size_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (job_id, direction, binding_id, ordinal, str(path), kind, mime_type, original_name, size_bytes),
                )
                return int(cursor.lastrowid)

    async def list_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            with self._connect() as db:
                rows = db.execute(
                    """SELECT id, direction, binding_id, ordinal, path, kind, mime_type,
                              original_name, size_bytes
                       FROM job_artifacts WHERE job_id = ? ORDER BY direction, binding_id, ordinal""",
                    (job_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    async def get_artifact(self, job_id: str, artifact_id: int) -> dict[str, Any] | None:
        async with self._lock:
            with self._connect() as db:
                row = db.execute(
                    """SELECT id, direction, binding_id, ordinal, path, kind, mime_type,
                              original_name, size_bytes
                       FROM job_artifacts WHERE job_id = ? AND id = ?""",
                    (job_id, artifact_id),
                ).fetchone()
        return dict(row) if row else None

    async def save_workflow(self, definition: dict[str, Any], *, status: str = "draft", builtin: bool = False) -> dict[str, Any]:
        workflow_id = str(definition["manifest"]["id"])
        name = str(definition["manifest"]["name"])
        now = time.time()
        async with self._lock:
            with self._connect() as db:
                latest = db.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM workflows WHERE id = ?", (workflow_id,)
                ).fetchone()[0]
                existing = None
                if builtin and latest:
                    existing = db.execute(
                        "SELECT status, name FROM workflows WHERE id = ? AND revision = ?",
                        (workflow_id, latest),
                    ).fetchone()
                    if existing:
                        status = existing["status"]
                        # The registry definition is refreshed from packaged files at
                        # startup, but a user-facing display name is a preference and
                        # must survive that refresh.
                        name = existing["name"]
                revision = max(int(definition["manifest"].get("revision", 1)), int(latest) + (0 if builtin and latest else 1))
                definition = json.loads(json.dumps(definition))
                definition["manifest"]["revision"] = revision
                if existing:
                    definition["manifest"]["name"] = name
                db.execute(
                    """INSERT OR REPLACE INTO workflows(
                        id, revision, status, name, definition_json, builtin, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (workflow_id, revision, status, name, json.dumps(definition, ensure_ascii=False), int(builtin), now, now),
                )
        return {"id": workflow_id, "revision": revision, "status": status, "name": name, "definition": definition, "builtin": builtin}

    async def list_workflows(self) -> list[dict[str, Any]]:
        async with self._lock:
            with self._connect() as db:
                rows = db.execute(
                    """SELECT w.* FROM workflows w JOIN (
                        SELECT id, MAX(revision) revision FROM workflows GROUP BY id
                    ) latest ON latest.id = w.id AND latest.revision = w.revision ORDER BY w.name"""
                ).fetchall()
        return [self._workflow_row(row) for row in rows]

    async def get_workflow(self, workflow_id: str, revision: int | None = None) -> dict[str, Any] | None:
        async with self._lock:
            with self._connect() as db:
                if revision is None:
                    row = db.execute(
                        "SELECT * FROM workflows WHERE id = ? ORDER BY revision DESC LIMIT 1", (workflow_id,)
                    ).fetchone()
                else:
                    row = db.execute(
                        "SELECT * FROM workflows WHERE id = ? AND revision = ?", (workflow_id, revision)
                    ).fetchone()
        return self._workflow_row(row) if row else None

    async def set_workflow_status(self, workflow_id: str, status: str) -> dict[str, Any] | None:
        if status not in {"draft", "enabled", "disabled"}:
            raise ValueError("invalid workflow status")
        async with self._lock:
            with self._connect() as db:
                row = db.execute(
                    "SELECT revision FROM workflows WHERE id = ? ORDER BY revision DESC LIMIT 1", (workflow_id,)
                ).fetchone()
                if row:
                    db.execute(
                        "UPDATE workflows SET status = ?, updated_at = ? WHERE id = ? AND revision = ?",
                        (status, time.time(), workflow_id, row[0]),
                    )
        return await self.get_workflow(workflow_id) if row else None

    async def backfill_legacy_workflows(self, definitions: dict[str, dict[str, Any]]) -> None:
        async with self._lock:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT * FROM jobs WHERE workflow_id IS NULL OR workflow_snapshot_json IS NULL"
                ).fetchall()
                for row in rows:
                    definition = definitions.get(row["preset_id"])
                    if definition is None:
                        continue
                    values = {
                        key: row[key] for key in (
                            "prompt", "duration_seconds", "aspect_ratio", "megapixels",
                            "seed", "scheduler", "sampler", "steps",
                        ) if key in row.keys()
                    }
                    db.execute(
                        """UPDATE jobs SET workflow_id = ?, workflow_revision = ?,
                                  workflow_snapshot_json = ?, input_values_json = ?
                           WHERE id = ?""",
                        (
                            row["preset_id"], int(definition["manifest"].get("revision", 1)),
                            json.dumps(definition, ensure_ascii=False),
                            json.dumps(values, ensure_ascii=False), row["id"],
                        ),
                    )

    @staticmethod
    def _workflow_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "revision": row["revision"], "status": row["status"],
            "name": row["name"], "definition": json.loads(row["definition_json"]),
            "builtin": bool(row["builtin"]), "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def _job_from_row(self, row: sqlite3.Row, files: list[dict[str, Any]]) -> dict[str, Any]:
        item = dict(row)
        snapshot = item.pop("workflow_snapshot_json", None)
        values = item.pop("input_values_json", None)
        item["workflow_snapshot"] = json.loads(snapshot) if snapshot else None
        item["input_values"] = json.loads(values) if values else {}
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

    async def existing_job_ids(self, job_ids: list[str]) -> set[str]:
        unique_ids = list(dict.fromkeys(str(job_id) for job_id in job_ids if str(job_id)))
        if not unique_ids:
            return set()
        marks = ",".join("?" for _ in unique_ids)
        async with self._lock:
            with self._connect() as db:
                rows = db.execute(
                    f"SELECT id FROM jobs WHERE id IN ({marks}) AND status != ?",
                    (*unique_ids, HIDDEN_STATUS),
                ).fetchall()
        return {str(row[0]) for row in rows}

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

    async def succeeded_jobs(self, *, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        """Return a bounded page of completed jobs for recovery scans."""

        async with self._lock:
            with self._connect() as db:
                query = "SELECT * FROM jobs WHERE status = 'succeeded' ORDER BY finished_at DESC"
                params: list[Any] = []
                if limit is not None:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([max(0, int(limit)), max(0, int(offset))])
                rows = db.execute(query, params).fetchall()
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
                       SELECT 1 FROM job_artifacts
                       WHERE job_artifacts.job_id = jobs.id AND job_artifacts.direction = 'output'
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
                rows = [
                    (str(row[0]), int(row[1]))
                    for row in db.execute(
                        """SELECT path, size_bytes FROM job_files
                           UNION ALL
                           SELECT path, size_bytes FROM job_artifacts"""
                    )
                ]
        return sum(size for _, size in _deduplicate_file_sizes(rows).values())

    async def tracked_paths(self) -> set[Path]:
        async with self._lock:
            with self._connect() as db:
                rows = [
                    (str(row[0]), 0)
                    for row in db.execute(
                        """SELECT path, size_bytes FROM job_files
                           UNION ALL
                           SELECT path, size_bytes FROM job_artifacts"""
                    )
                ]
        return {path for path, _ in _deduplicate_file_sizes(rows).values()}

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
