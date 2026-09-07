from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any


DEFAULT_OLLAMA_MODEL = "gemma4:e4b"
_ARTIFACT_RECONCILE_INTERVAL = 30.0


def _snapshot_ollama_model(job: dict[str, Any]) -> str:
    snapshot = job.get("workflow_snapshot")
    manifest = snapshot.get("manifest") if isinstance(snapshot, dict) else None
    if isinstance(manifest, dict):
        parameters = manifest.get("parameters")
        if isinstance(parameters, dict):
            spec = parameters.get("ollama_model")
            if isinstance(spec, dict):
                value = spec.get("default")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        locked = manifest.get("locked")
        if isinstance(locked, list):
            for assertion in locked:
                if not isinstance(assertion, dict) or assertion.get("class_type") != "H3PromptStandardizer":
                    continue
                inputs = assertion.get("inputs")
                value = inputs.get("ollama_model") if isinstance(inputs, dict) else None
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return DEFAULT_OLLAMA_MODEL


def _install_database() -> None:
    from . import db as db_module

    if hasattr(db_module.Database, "output_artifact_jobs_v045"):
        return

    async def output_artifact_jobs_v045(self) -> list[dict[str, Any]]:
        active = sorted(db_module.ACTIVE_STATUSES)
        placeholders = ",".join("?" for _ in active)
        async with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""SELECT jobs.id AS job_id, jobs.status AS job_status,
                               job_artifacts.id AS artifact_id,
                               job_artifacts.path AS artifact_path,
                               job_artifacts.kind AS artifact_kind
                        FROM jobs
                        JOIN job_artifacts ON job_artifacts.job_id = jobs.id
                        WHERE job_artifacts.direction = 'output'
                          AND jobs.status NOT IN ({placeholders})
                        ORDER BY jobs.id, job_artifacts.id""",
                    active,
                ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            job_id = str(row["job_id"])
            item = grouped.setdefault(
                job_id,
                {"id": job_id, "status": str(row["job_status"]), "outputs": []},
            )
            item["outputs"].append(
                {
                    "id": int(row["artifact_id"]),
                    "path": str(row["artifact_path"]),
                    "kind": str(row["artifact_kind"]),
                }
            )
        return list(grouped.values())

    async def remove_output_artifact_v045(
        self, job_id: str, artifact_id: int, path: str
    ) -> bool:
        async with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """DELETE FROM job_artifacts
                       WHERE id = ? AND job_id = ? AND direction = 'output' AND path = ?""",
                    (artifact_id, job_id, path),
                )
                if cursor.rowcount:
                    connection.execute(
                        "DELETE FROM job_files WHERE job_id = ? AND role = 'output' AND path = ?",
                        (job_id, path),
                    )
                return cursor.rowcount == 1

    db_module.Database.output_artifact_jobs_v045 = output_artifact_jobs_v045
    db_module.Database.remove_output_artifact_v045 = remove_output_artifact_v045


def _install_preset_behavior() -> None:
    from . import preset as preset_module

    if getattr(preset_module.Preset.validate_parameters, "_v045_ollama_model", False):
        return

    original_validate_parameters = preset_module.Preset.validate_parameters

    def validate_parameters_v045(
        self,
        values: dict[str, Any],
        *,
        allow_empty_prompt: bool = False,
    ) -> dict[str, Any]:
        prepared = dict(values)
        spec = self.manifest.get("parameters", {}).get("ollama_model")
        if isinstance(spec, dict):
            value = prepared.get("ollama_model", spec.get("default", DEFAULT_OLLAMA_MODEL))
            if value is None:
                value = ""
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    default = spec.get("default", DEFAULT_OLLAMA_MODEL)
                    value = str(default).strip() or DEFAULT_OLLAMA_MODEL
                prepared["ollama_model"] = value
        return original_validate_parameters(
            self, prepared, allow_empty_prompt=allow_empty_prompt
        )

    validate_parameters_v045._v045_ollama_model = True  # type: ignore[attr-defined]
    preset_module.Preset.validate_parameters = validate_parameters_v045


def _install_job_service() -> None:
    from . import jobs as jobs_module
    from .files import FileValidationError
    from .v042 import FL2VA_PRESET_IDS

    if getattr(jobs_module.JobService.reconcile_once, "_v045_artifact_sync", False):
        return

    original_reconcile_once = jobs_module.JobService.reconcile_once
    original_retry = jobs_module.JobService.retry

    async def purge_v045(self, job_id: str) -> None:
        job = await self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] not in jobs_module.TERMINAL_STATUSES | {jobs_module.HIDDEN_STATUS}:
            raise jobs_module.PresetError("运行中或排队中的任务不能清理文件")

        artifacts = await self.db.list_artifacts(job_id)
        seen: set[str] = set()
        try:
            for artifact in artifacts:
                path = Path(str(artifact["path"]))
                seen.add(str(path))
                if not path.exists():
                    continue
                role = "output" if artifact.get("direction") == "output" else str(artifact.get("binding_id") or "input")
                self.files.delete_exact(path, role)
            for file in job.get("files", []):
                path = Path(str(file["path"]))
                if str(path) in seen or not path.exists():
                    continue
                self.files.delete_exact(path, str(file["role"]))
            await self.db.delete_job(job_id)
        except Exception:
            current = await self.db.get_job(job_id)
            if current is not None:
                await self.db.update_job(
                    job_id,
                    status=current["status"],
                    stage="清理失败",
                    error_code="purge_failed",
                    error_summary="部分文件清理失败，请检查权限后重试",
                )
            raise
        self.events.publish("job_deleted", {"id": job_id})

    async def reconcile_output_artifacts_v045(self) -> None:
        candidates = await self.db.output_artifact_jobs_v045()

        async def probe(artifact: dict[str, Any]) -> tuple[str, Path]:
            path = Path(str(artifact["path"]))
            try:
                await asyncio.to_thread(self.files.validate_artifact_file, path)
            except FileNotFoundError:
                return "missing", path
            except (OSError, FileValidationError):
                return "uncertain", path
            return "present", path

        for candidate in candidates:
            job_id = str(candidate["id"])
            current = await self.db.get_job(job_id)
            if current is None or current.get("status") in jobs_module.ACTIVE_STATUSES:
                continue

            states = {
                id(artifact): await probe(artifact)
                for artifact in candidate.get("outputs", [])
            }
            missing = [
                artifact for artifact in candidate.get("outputs", [])
                if states[id(artifact)][0] == "missing"
            ]
            existing = [
                artifact for artifact in candidate.get("outputs", [])
                if states[id(artifact)][0] == "present"
            ]
            uncertain = [
                artifact for artifact in candidate.get("outputs", [])
                if states[id(artifact)][0] == "uncertain"
            ]

            if not missing or uncertain:
                continue

            if not existing:
                current = await self.db.get_job(job_id)
                if current is None or current.get("status") in jobs_module.ACTIVE_STATUSES:
                    continue
                rechecked = [await probe(artifact) for artifact in candidate.get("outputs", [])]
                if any(state != "missing" for state, _ in rechecked):
                    continue
                current = await self.db.get_job(job_id)
                if current is None or current.get("status") in jobs_module.ACTIVE_STATUSES:
                    continue
                try:
                    await self.purge(job_id)
                except KeyError:
                    pass
                continue

            changed = False
            for artifact in missing:
                changed = await self.db.remove_output_artifact_v045(
                    job_id,
                    int(artifact["id"]),
                    str(artifact["path"]),
                ) or changed
            if changed:
                updated = await self.db.get_job(job_id)
                if updated is not None:
                    self.events.publish("job", self.public_job(updated))

    async def reconcile_output_artifacts_if_due_v045(self) -> None:
        now = time.monotonic()
        last = float(getattr(self, "_last_artifact_reconcile_v045", 0.0))
        if now - last < _ARTIFACT_RECONCILE_INTERVAL:
            return
        self._last_artifact_reconcile_v045 = now
        await reconcile_output_artifacts_v045(self)

    async def reconcile_once_v045(self) -> None:
        try:
            await original_reconcile_once(self)
        except jobs_module.ComfyError:
            await reconcile_output_artifacts_if_due_v045(self)
            raise
        await reconcile_output_artifacts_if_due_v045(self)

    async def retry_v045(self, job_id: str) -> dict[str, Any]:
        source = await self.db.get_job(job_id)
        draft = await original_retry(self, job_id)
        if source is None or str(source.get("preset_id") or "") not in FL2VA_PRESET_IDS:
            return draft
        values = dict(draft.get("values") or {})
        value = values.get("ollama_model")
        if not isinstance(value, str) or not value.strip():
            value = _snapshot_ollama_model(source)
        value = value.strip()
        values["ollama_model"] = value
        draft["values"] = values
        draft["ollama_model"] = value
        return draft

    purge_v045._v045_artifact_sync = True  # type: ignore[attr-defined]
    reconcile_output_artifacts_v045._v045_artifact_sync = True  # type: ignore[attr-defined]
    reconcile_output_artifacts_if_due_v045._v045_artifact_sync = True  # type: ignore[attr-defined]
    reconcile_once_v045._v045_artifact_sync = True  # type: ignore[attr-defined]
    retry_v045._v045_ollama_model = True  # type: ignore[attr-defined]
    jobs_module.JobService.purge = purge_v045
    jobs_module.JobService.reconcile_output_artifacts_v045 = reconcile_output_artifacts_v045
    jobs_module.JobService.reconcile_output_artifacts_if_due_v045 = reconcile_output_artifacts_if_due_v045
    jobs_module.JobService.reconcile_once = reconcile_once_v045
    jobs_module.JobService.retry = retry_v045


def install() -> None:
    """Install v0.4.5 artifact-history sync and FL2VA Ollama model selection."""

    _install_database()
    _install_preset_behavior()
    _install_job_service()
