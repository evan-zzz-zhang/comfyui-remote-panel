from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from comfyui_remote_panel.jobs import JobService
from comfyui_remote_panel.preset import preset_from_definition
from comfyui_remote_panel.workflow_config import build_definition, inspect_api_workflow
from test_workflow_analysis import object_info, wai_img2img_workflow
from test_workflow_runtime import wai_config


def generic_service() -> tuple[JobService, object]:
    analysis, config = wai_config()
    preset = preset_from_definition(build_definition(wai_img2img_workflow(), config, analysis))
    preset.manifest["stages"] = {}
    db = Mock()
    files = Mock()
    files.role_kind.return_value = None
    service = JobService(db, files, Mock(), {preset.id: preset}, Mock())
    return service, preset


def test_generic_progress_uses_real_progress_and_reserves_100_for_success() -> None:
    service, preset = generic_service()
    base = {
        "id": "job-1",
        "preset_id": preset.id,
        "seed": "0",
        "files": [],
        "stage": "采样",
        "status": "running",
    }

    halfway = service.public_job({**base, "progress_value": 5, "progress_max": 10})
    assert halfway["progress_percent"] == 50

    sampler_done = service.public_job({**base, "progress_value": 10, "progress_max": 10})
    assert sampler_done["progress_percent"] == 95

    succeeded = service.public_job({**base, "status": "succeeded", "progress_value": 10, "progress_max": 10})
    assert succeeded["progress_percent"] == 100


@pytest.mark.asyncio
async def test_generic_progress_state_does_not_treat_completed_helper_as_overall_progress() -> None:
    service, preset = generic_service()
    service.db.update_active_job = AsyncMock(return_value={"id": "job-1", "status": "running"})

    await service._handle_progress_state(
        "job-1",
        preset,
        {"nodes": {"helper": {"state": "finished", "value": 1, "max": 1}}},
    )

    kwargs = service.db.update_active_job.await_args.kwargs
    assert kwargs["status"] == "running"
    assert "progress_value" not in kwargs
    assert "progress_max" not in kwargs
