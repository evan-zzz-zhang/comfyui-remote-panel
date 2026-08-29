from __future__ import annotations

import time
from typing import Any

from .comfy import ComfyError
from .db import ACTIVE_STATUSES, TERMINAL_STATUSES


_GENERIC_EXECUTION_FAILURE = "ComfyUI 执行失败，请检查本机日志"
_SUCCESS_STATUSES = {"success", "succeeded", "completed"}
_FAILURE_STATUSES = {"error", "failed", "failure"}
_INTERRUPTED_STATUSES = {"cancelled", "canceled", "interrupted"}


def _history_terminal_kind(entry: Any) -> str | None:
    """Return only explicit terminal evidence from a ComfyUI history entry.

    A history row may become visible before ComfyUI has finalized its status.
    Treating that transient row as a failure makes Panel restarts race with
    ComfyUI's history persistence. Unknown/incomplete history is therefore not
    terminal evidence.
    """

    if not isinstance(entry, dict):
        return None
    status_data = entry.get("status")
    if not isinstance(status_data, dict):
        return None

    status_text = str(status_data.get("status_str", "")).strip().lower()
    messages = status_data.get("messages", [])
    message_types = {
        str(message[0])
        for message in messages if isinstance(message, list) and message
    }

    if "execution_error" in message_types:
        return "failed"
    if "execution_interrupted" in message_types:
        return "interrupted"
    if (
        status_data.get("completed") is True
        or status_text in _SUCCESS_STATUSES
        or "execution_success" in message_types
    ):
        return "succeeded"
    if status_text in _INTERRUPTED_STATUSES:
        return "interrupted"
    if status_text in _FAILURE_STATUSES:
        return "failed"
    return None


def _is_legacy_false_failure_candidate(job: dict[str, Any]) -> bool:
    return (
        job.get("status") == "failed"
        and job.get("error_code") == "execution_failed"
        and job.get("error_summary") == _GENERIC_EXECUTION_FAILURE
        and not job.get("has_video")
    )


def install() -> None:
    """Install v0.4.3 task/history reconciliation hardening.

    The invariant is that Panel may enter a terminal state only from explicit
    ComfyUI terminal evidence. A WebSocket execution_success event is itself
    explicit success evidence even when /history is a few milliseconds behind.
    """

    from . import jobs as jobs_module

    if getattr(jobs_module.JobService._apply_history, "_v043_task_reconciliation", False):
        return

    original_apply_history = jobs_module.JobService._apply_history
    original_handle_ws_event = jobs_module.JobService.handle_ws_event
    original_recover_missing_outputs = jobs_module.JobService._recover_missing_outputs

    async def apply_history_v043(
        self,
        job: dict[str, Any],
        entry: dict[str, Any],
    ) -> dict[str, Any] | None:
        current = await self.db.get_job(job["id"])
        if current is None:
            return None

        terminal_kind = _history_terminal_kind(entry)
        if terminal_kind is None:
            if current["status"] in TERMINAL_STATUSES:
                return current
            return await self.db.update_active_job(
                current["id"],
                stage="确认最终状态",
                missing_observations=0,
                missing_first_at=None,
            )

        # v0.4.2 could permanently mark a successfully generated task as failed
        # when execution_success arrived just before /history became final. Repair
        # only that exact generic false-failure signature. A specific WebSocket
        # execution_error remains authoritative and must not be overwritten by a
        # delayed/stale success result from a concurrent reconcile pass.
        if _is_legacy_false_failure_candidate(current) and terminal_kind == "succeeded":
            # Keep older wrappers in the chain (notably the v0.4.2 standardized
            # prompt capture) before correcting the terminal job itself.
            await original_apply_history(self, current, entry)
            await self._capture_output(current["id"], entry)
            return await self.db.update_job(
                current["id"],
                status="succeeded",
                stage="已完成",
                finished_at=time.time(),
                queue_position=None,
                error_code=None,
                error_summary=None,
                recovery_attempts=0,
                recovery_next_at=None,
                recovery_last_error=None,
                missing_observations=0,
                missing_first_at=None,
            )

        if current["status"] in TERMINAL_STATUSES:
            # A succeeded job may still be waiting for history-backed metadata
            # such as the standardized prompt. Let the previous wrapper inspect
            # explicit success history without changing the terminal state.
            if current["status"] == "succeeded" and terminal_kind == "succeeded":
                await original_apply_history(self, current, entry)
                return await self.db.get_job(current["id"])
            return current

        return await original_apply_history(self, current, entry)

    async def handle_ws_event_v043(self, event: dict[str, Any]) -> None:
        if event.get("type") != "execution_success":
            await original_handle_ws_event(self, event)
            return

        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        job_id = data.get("prompt_id")
        if not isinstance(job_id, str):
            return
        job = await self.db.get_job(job_id)
        if job is None:
            return

        entry: dict[str, Any] | None = None
        try:
            history = await self.comfy.history(job_id)
            candidate = history.get(job_id) if isinstance(history, dict) else None
            if isinstance(candidate, dict):
                entry = candidate
        except ComfyError:
            pass

        if entry is not None and _history_terminal_kind(entry) is not None:
            updated = await self._apply_history(job, entry)
        elif job["status"] in ACTIVE_STATUSES:
            # execution_success is already terminal evidence. Do not convert a
            # temporarily empty /history response into a generic failure. Output
            # registration remains recoverable from history on the next pass.
            _, updated = await self.db.update_job_if_status(
                job_id,
                ACTIVE_STATUSES,
                status="succeeded",
                stage="已完成",
                finished_at=time.time(),
                queue_position=None,
                error_code=None,
                error_summary=None,
                recovery_attempts=0,
                recovery_next_at=None,
                recovery_last_error=None,
                missing_observations=0,
                missing_first_at=None,
            )
        elif _is_legacy_false_failure_candidate(job) and entry is not None:
            updated = await self._apply_history(job, entry)
        else:
            updated = job

        if updated:
            self.events.publish("job", self.public_job(updated))

    async def recover_missing_outputs_v043(self) -> None:
        # If execution_success had to be trusted before history was finalized,
        # first give history-backed metadata wrappers a chance to catch up.
        for job in await self.db.succeeded_without_output():
            try:
                history = await self.comfy.history(job["id"])
            except ComfyError:
                continue
            entry = history.get(job["id"]) if isinstance(history, dict) else None
            if isinstance(entry, dict) and _history_terminal_kind(entry) == "succeeded":
                await self._apply_history(job, entry)

        await original_recover_missing_outputs(self)

        # One release of v0.4.2 could already have persisted the race as a
        # generic failed terminal job. Re-check only that narrow signature for
        # 24 hours, but require explicit ComfyUI success evidence. Disk files do
        # not redefine task state.
        page = await self.db.list_jobs(1, 100, statuses={"failed"})
        now = time.time()
        for job in page["items"]:
            if not _is_legacy_false_failure_candidate(job):
                continue
            finished_at = float(job.get("finished_at") or job["created_at"])
            if now - finished_at > 24 * 60 * 60:
                continue
            try:
                history = await self.comfy.history(job["id"])
            except ComfyError:
                continue
            entry = history.get(job["id"]) if isinstance(history, dict) else None
            if not isinstance(entry, dict) or _history_terminal_kind(entry) != "succeeded":
                continue
            updated = await self._apply_history(job, entry)
            if updated:
                self.events.publish("job", self.public_job(updated))

    apply_history_v043._v043_task_reconciliation = True  # type: ignore[attr-defined]
    handle_ws_event_v043._v043_task_reconciliation = True  # type: ignore[attr-defined]
    recover_missing_outputs_v043._v043_task_reconciliation = True  # type: ignore[attr-defined]
    jobs_module.JobService._apply_history = apply_history_v043
    jobs_module.JobService.handle_ws_event = handle_ws_event_v043
    jobs_module.JobService._recover_missing_outputs = recover_missing_outputs_v043
