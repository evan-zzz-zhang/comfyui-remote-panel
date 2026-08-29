from __future__ import annotations

import time
from pathlib import Path

import pytest
from aiohttp import FormData, web

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}
GENERIC_FAILURE = "ComfyUI 执行失败，请检查本机日志"


@pytest.fixture
async def comfy_server_v043(aiohttp_server):
    app = web.Application()
    app["history"] = {}
    app["submitted"] = []

    async def stats(_):
        return web.json_response({"system": {"comfyui_version": "0.30.0"}, "devices": []})

    async def queue(_):
        return web.json_response({"queue_running": [], "queue_pending": []})

    async def submit(request):
        body = await request.json()
        app["submitted"].append(body)
        return web.json_response({"prompt_id": body["prompt_id"], "number": 1, "node_errors": {}})

    async def history(request):
        job_id = request.match_info["job_id"]
        entry = app["history"].get(job_id)
        return web.json_response({job_id: entry} if entry is not None else {})

    async def cancel(_):
        return web.json_response({"cancelled": False})

    app.router.add_get("/system_stats", stats)
    app.router.add_get("/queue", queue)
    app.router.add_post("/prompt", submit)
    app.router.add_get("/history/{job_id}", history)
    app.router.add_post("/api/jobs/{job_id}/cancel", cancel)
    return await aiohttp_server(app)


@pytest.fixture
async def panel_client_v043(tmp_path, comfy_server_v043, aiohttp_client):
    config = Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url=str(comfy_server_v043.make_url("/")).rstrip("/"),
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )
    client = await aiohttp_client(create_app(config))
    for preset in client.app["presets"].values():
        preset.available = True
        preset.diagnostics = []
    return client


async def _create_job(client, prompt: str = "reconciliation test") -> dict:
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-fl2va-v4step600")
    form.add_field("prompt", prompt)
    response = await client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    return await response.json()


@pytest.mark.asyncio
async def test_execution_success_does_not_fail_when_history_is_not_ready(panel_client_v043):
    created = await _create_job(panel_client_v043)

    await panel_client_v043.app["jobs"].handle_ws_event({
        "type": "execution_success",
        "data": {"prompt_id": created["id"]},
    })

    stored = await panel_client_v043.app["db"].get_job(created["id"])
    assert stored["status"] == "succeeded"
    assert stored["error_code"] is None
    assert stored["error_summary"] is None


@pytest.mark.asyncio
async def test_incomplete_history_keeps_active_job_non_terminal(
    panel_client_v043, comfy_server_v043
):
    created = await _create_job(panel_client_v043)
    comfy_server_v043.app["history"][created["id"]] = {
        "status": {"completed": False, "status_str": "running", "messages": []},
        "outputs": {},
    }

    await panel_client_v043.app["jobs"].reconcile_once()

    stored = await panel_client_v043.app["db"].get_job(created["id"])
    assert stored["status"] == "queued"
    assert stored["stage"] == "确认最终状态"
    assert stored["error_code"] is None


@pytest.mark.asyncio
async def test_message_only_success_history_is_not_misclassified(
    panel_client_v043, comfy_server_v043
):
    created = await _create_job(panel_client_v043)
    comfy_server_v043.app["history"][created["id"]] = {
        "status": {
            "completed": False,
            "status_str": "",
            "messages": [["execution_success", {"timestamp": 1}]],
        },
        "outputs": {},
    }

    await panel_client_v043.app["jobs"].reconcile_once()

    stored = await panel_client_v043.app["db"].get_job(created["id"])
    assert stored["status"] == "succeeded"
    assert stored["error_code"] is None
    assert stored["error_summary"] is None


@pytest.mark.asyncio
async def test_explicit_history_error_still_marks_job_failed(
    panel_client_v043, comfy_server_v043
):
    created = await _create_job(panel_client_v043)
    comfy_server_v043.app["history"][created["id"]] = {
        "status": {
            "completed": False,
            "status_str": "error",
            "messages": [["execution_error", {"exception_message": "synthetic failure"}]],
        },
        "outputs": {},
    }

    await panel_client_v043.app["jobs"].reconcile_once()

    stored = await panel_client_v043.app["db"].get_job(created["id"])
    assert stored["status"] == "failed"
    assert stored["error_code"] == "execution_failed"
    assert stored["error_summary"] == "synthetic failure"


@pytest.mark.asyncio
async def test_v042_generic_false_failure_repairs_output_after_panel_restart(
    panel_client_v043, comfy_server_v043
):
    created = await _create_job(panel_client_v043, "restart recovery")
    job_id = created["id"]
    await panel_client_v043.app["db"].update_job(
        job_id,
        status="failed",
        stage="失败",
        error_code="execution_failed",
        error_summary=GENERIC_FAILURE,
        finished_at=time.time(),
    )

    files = panel_client_v043.app["files"]
    storage_key = files.storage_key(job_id)
    raw_name = f"{storage_key}_00001_.mp4"
    raw_path = files.output_root / raw_name
    raw_path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)

    comfy_server_v043.app["history"][job_id] = {
        "status": {
            "completed": True,
            "status_str": "success",
            "messages": [["execution_success", {"timestamp": 1}]],
        },
        "outputs": {
            "92": {
                "videos": [{
                    "filename": raw_name,
                    "subfolder": "h3_remote",
                    "type": "output",
                }]
            }
        },
    }

    await panel_client_v043.app["jobs"]._recover_missing_outputs()

    stored = await panel_client_v043.app["db"].get_job(job_id)
    final_path = files.output_root / files.flat_output_name(job_id)
    assert stored["status"] == "succeeded"
    assert stored["error_code"] is None
    assert stored["has_video"] is True
    assert final_path.exists()
    assert not raw_path.exists()
