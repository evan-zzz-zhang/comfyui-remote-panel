from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


_RETRY_MEDIA_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "v041_retry_media_context", default=None
)
_ORIGINAL_PROCESS_RESOLUTION = None


def _path_key(path: Path) -> str:
    return str(path.resolve())


def _extract_image_output_metadata(path: Path) -> dict[str, Any] | None:
    try:
        with Image.open(path) as image:
            image_format = image.format or path.suffix.lstrip(".")
            return {
                "width": int(image.width),
                "height": int(image.height),
                "format": str(image_format).upper(),
            }
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        return None


def _same_resolution_policy(
    metadata: dict[str, Any], policy: str, target_megapixels: float | None
) -> bool:
    source_policy = str(metadata.get("resolution_policy") or "original")
    if source_policy != policy:
        return False
    if policy == "original":
        return True
    if policy != "auto" or target_megapixels is None:
        return False
    try:
        source_target = float(metadata.get("target_megapixels"))
    except (TypeError, ValueError):
        return False
    return abs(source_target - float(target_megapixels)) < 1e-9


def _process_resolution_v041(
    path: Path, policy: str, target_megapixels: float | None
) -> dict[str, Any]:
    context = _RETRY_MEDIA_CONTEXT.get()
    if context is not None:
        retained = context.get("prepared_by_destination", {}).get(_path_key(path))
        if retained and _same_resolution_policy(retained, policy, target_megapixels):
            return dict(retained)
    if _ORIGINAL_PROCESS_RESOLUTION is None:
        raise RuntimeError("v0.4.1 image processing integration is not installed")
    return _ORIGINAL_PROCESS_RESOLUTION(path, policy, target_megapixels)


def _decode_artifact_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    raw_metadata = item.pop("metadata_json", None)
    metadata = None
    if raw_metadata:
        try:
            value = json.loads(raw_metadata)
            metadata = value if isinstance(value, dict) else None
        except (TypeError, ValueError):
            metadata = None
    item["metadata"] = metadata
    return item


async def _backfill_artifact_metadata(db, artifacts: list[dict[str, Any]]) -> None:
    for artifact in artifacts:
        if (
            artifact.get("direction") != "output"
            or artifact.get("kind") != "image"
            or artifact.get("metadata") is not None
        ):
            continue
        metadata = await asyncio.to_thread(
            _extract_image_output_metadata, Path(str(artifact["path"]))
        )
        if metadata is None:
            continue
        async with db._lock:
            with db._connect() as connection:
                connection.execute(
                    "UPDATE job_artifacts SET metadata_json = ? WHERE id = ? AND metadata_json IS NULL",
                    (json.dumps(metadata, ensure_ascii=False), int(artifact["id"])),
                )
        artifact["metadata"] = metadata


def _install_database() -> None:
    from . import db as db_module

    if getattr(db_module.Database.initialize, "_v041_media_metadata", False):
        return

    original_initialize = db_module.Database.initialize

    async def initialize_v041(self) -> None:
        await original_initialize(self)
        async with self._lock:
            with self._connect() as connection:
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(job_artifacts)").fetchall()
                }
                if "metadata_json" not in columns:
                    connection.execute(
                        "ALTER TABLE job_artifacts ADD COLUMN metadata_json TEXT"
                    )

    initialize_v041._v041_media_metadata = True  # type: ignore[attr-defined]
    db_module.Database.initialize = initialize_v041

    async def add_artifact_v041(
        self,
        job_id: str,
        direction: str,
        binding_id: str,
        ordinal: int,
        path: Path,
        kind: str,
        mime_type: str | None,
        original_name: str | None,
        size_bytes: int,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        if metadata is None and direction == "output" and kind == "image":
            metadata = await asyncio.to_thread(_extract_image_output_metadata, Path(path))
        raw_metadata = json.dumps(metadata, ensure_ascii=False) if metadata else None
        async with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """INSERT OR REPLACE INTO job_artifacts(
                        job_id, direction, binding_id, ordinal, path, kind,
                        mime_type, original_name, size_bytes, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job_id,
                        direction,
                        binding_id,
                        ordinal,
                        str(path),
                        kind,
                        mime_type,
                        original_name,
                        size_bytes,
                        raw_metadata,
                    ),
                )
                return int(cursor.lastrowid)

    db_module.Database.add_artifact = add_artifact_v041

    async def list_artifacts_v041(self, job_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """SELECT id, direction, binding_id, ordinal, path, kind, mime_type,
                              original_name, size_bytes, metadata_json
                       FROM job_artifacts WHERE job_id = ?
                       ORDER BY direction, binding_id, ordinal""",
                    (job_id,),
                ).fetchall()
        artifacts = [_decode_artifact_row(row) for row in rows]
        await _backfill_artifact_metadata(self, artifacts)
        return artifacts

    db_module.Database.list_artifacts = list_artifacts_v041

    async def get_artifact_v041(
        self, job_id: str, artifact_id: int
    ) -> dict[str, Any] | None:
        async with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """SELECT id, direction, binding_id, ordinal, path, kind, mime_type,
                              original_name, size_bytes, metadata_json
                       FROM job_artifacts WHERE job_id = ? AND id = ?""",
                    (job_id, artifact_id),
                ).fetchone()
        return _decode_artifact_row(row) if row else None

    db_module.Database.get_artifact = get_artifact_v041


def _install_file_store() -> None:
    from . import files as files_module

    if not hasattr(files_module.FileStore, "validate_input_file"):
        def validate_input_file(self, path: Path) -> Path:
            resolved = path.resolve(strict=True)
            self._assert_managed_file(resolved, self.input_root)
            return resolved

        files_module.FileStore.validate_input_file = validate_input_file  # type: ignore[attr-defined]

    if getattr(files_module.FileStore.copy_input_async, "_v041_retry_reuse", False):
        return

    original_copy_input_async = files_module.FileStore.copy_input_async

    async def copy_input_async_v041(self, source: Path, job_id: str, role: str):
        context = _RETRY_MEDIA_CONTEXT.get()
        source_key = _path_key(Path(source))
        try:
            copied = await original_copy_input_async(self, source, job_id, role)
        except FileNotFoundError as exc:
            if context is not None and source_key in context.get("retained_sources", set()):
                raise files_module.FileValidationError(
                    "原任务参考素材已不存在，无法继续沿用"
                ) from exc
            raise
        if context is not None:
            metadata = context.get("metadata_by_source", {}).get(source_key)
            if metadata:
                context.setdefault("prepared_by_destination", {})[
                    _path_key(Path(copied["path"]))
                ] = dict(metadata)
        return copied

    copy_input_async_v041._v041_retry_reuse = True  # type: ignore[attr-defined]
    files_module.FileStore.copy_input_async = copy_input_async_v041


def _install_job_service() -> None:
    from . import jobs as jobs_module

    if not getattr(jobs_module.JobService.retry, "_v041_retained_media", False):
        original_retry = jobs_module.JobService.retry

        async def retry_v041(self, job_id: str) -> dict[str, Any]:
            draft = await original_retry(self, job_id)
            keep_roles = set(draft.get("retry_keep_roles") or draft.get("input_roles") or [])
            artifacts = await self.db.list_artifacts(job_id)
            retained_media = []
            for artifact in artifacts:
                role = str(artifact.get("binding_id") or "")
                if artifact.get("direction") != "input" or role not in keep_roles:
                    continue
                retained_media.append(
                    {
                        "artifact_id": int(artifact["id"]),
                        "role": role,
                        "kind": str(artifact.get("kind") or "file"),
                        "size_bytes": int(artifact.get("size_bytes") or 0),
                    }
                )
            draft["retained_media"] = retained_media
            return draft

        retry_v041._v041_retained_media = True  # type: ignore[attr-defined]
        jobs_module.JobService.retry = retry_v041

    if getattr(jobs_module.JobService.create, "_v041_retry_reuse", False):
        return

    original_create = jobs_module.JobService.create

    async def create_v041(
        self,
        fields: dict[str, Any],
        uploaded: list[dict[str, Any]],
        job_id: str | None = None,
        *,
        is_test: bool = False,
    ) -> dict[str, Any]:
        source_id = fields.get("retry_source_id")
        context = None
        if source_id:
            source = await self.db.get_job(str(source_id))
            if source is not None:
                source_metadata = source.get("media_metadata") or {}
                retained_sources: set[str] = set()
                metadata_by_source: dict[str, dict[str, Any]] = {}
                for file in source.get("files", []):
                    source_key = _path_key(Path(str(file["path"])))
                    retained_sources.add(source_key)
                    role = str(file.get("role") or "")
                    metadata = source_metadata.get(role)
                    if isinstance(metadata, dict):
                        metadata_by_source[source_key] = dict(metadata)
                context = {
                    "retained_sources": retained_sources,
                    "metadata_by_source": metadata_by_source,
                    "prepared_by_destination": {},
                }
        token = _RETRY_MEDIA_CONTEXT.set(context)
        try:
            return await original_create(
                self, fields, uploaded, job_id, is_test=is_test
            )
        finally:
            _RETRY_MEDIA_CONTEXT.reset(token)

    create_v041._v041_retry_reuse = True  # type: ignore[attr-defined]
    jobs_module.JobService.create = create_v041


def _install_resolution_reuse() -> None:
    global _ORIGINAL_PROCESS_RESOLUTION
    from . import v04 as v04_module

    if getattr(v04_module._process_resolution, "_v041_retry_reuse", False):
        return
    _ORIGINAL_PROCESS_RESOLUTION = v04_module._process_resolution
    _process_resolution_v041._v041_retry_reuse = True  # type: ignore[attr-defined]
    v04_module._process_resolution = _process_resolution_v041


def _install_app() -> None:
    from aiohttp import web

    from . import app as app_module
    from .files import FileValidationError

    if getattr(app_module.create_app, "_v041_input_preview", False):
        return

    original_create_app = app_module.create_app

    def create_app_v041(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)

        async def input_media(request: web.Request) -> web.StreamResponse:
            job_id = request.match_info["job_id"]
            try:
                artifact_id = int(request.match_info["artifact_id"])
            except (TypeError, ValueError):
                return app_module.json_error("input media not found", 404, "not_found")
            if await application["db"].get_job(job_id) is None:
                return app_module.json_error("input media not found", 404, "not_found")
            artifact = await application["db"].get_artifact(job_id, artifact_id)
            if artifact is None or artifact.get("direction") != "input":
                return app_module.json_error("input media not found", 404, "not_found")
            try:
                path = application["files"].validate_input_file(Path(str(artifact["path"])))
            except (FileNotFoundError, OSError, FileValidationError):
                return app_module.json_error("input media not found", 404, "not_found")
            return web.FileResponse(
                path,
                headers={"Cache-Control": "private, no-cache"},
            )

        application.router.add_get(
            "/api/jobs/{job_id}/inputs/{artifact_id}", input_media
        )
        return application

    create_app_v041._v041_input_preview = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v041


def install() -> None:
    """Install v0.4.1 media continuity as additive compatibility layers."""

    _install_database()
    _install_file_store()
    _install_job_service()
    _install_resolution_reuse()
    _install_app()
