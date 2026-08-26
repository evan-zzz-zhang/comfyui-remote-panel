from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from test_app import LOGIN, comfy_server, panel_client
from test_workflow_config import remote_config, save_image_workflow


async def create_generic_workflow(panel_client):
    response = await panel_client.post(
        "/api/workflows",
        json={"workflow": save_image_workflow(), "config": remote_config()},
        headers=LOGIN,
    )
    assert response.status == 201, await response.text()
    item = await response.json()
    enabled = await panel_client.post(
        f"/api/workflows/{item['id']}/status",
        json={"status": "enabled"},
        headers=LOGIN,
    )
    assert enabled.status == 200, await enabled.text()
    return item["id"]


async def add_output_artifact(panel_client, job_id: str) -> None:
    await panel_client.app["db"].add_artifact(
        job_id,
        "output",
        "primary",
        0,
        Path("fixture-output") / f"{job_id}.png",
        "image",
        "image/png",
        "result.png",
        1,
    )


@pytest.mark.asyncio
async def test_runtime_preflight_persists_pass_and_fail_without_new_revision(panel_client, comfy_server):
    workflow_id = await create_generic_workflow(panel_client)
    before = await (await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)).json()
    revision = before["revision"]
    assert before["definition"]["manifest"]["preflight"]["runtime"]["status"] == "WARN"

    test_response = await panel_client.post(
        f"/api/workflows/{workflow_id}/test",
        json={"positive_prompt": "runtime pass", "steps": 10},
        headers=LOGIN,
    )
    assert test_response.status == 201, await test_response.text()
    test_job = await test_response.json()
    history_entry = {
        "status": {"completed": True, "status_str": "success", "messages": []},
        "outputs": {},
    }
    panel_client.app["comfy"].history = AsyncMock(return_value={test_job["id"]: history_entry})
    await panel_client.app["jobs"].handle_ws_event({
        "type": "execution_success",
        "data": {"prompt_id": test_job["id"]},
    })

    pending = await (await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)).json()
    runtime = pending["definition"]["manifest"]["preflight"]["runtime"]
    assert pending["revision"] == revision
    assert runtime["status"] == "WARN"
    assert runtime["message"] == "Runtime execution passed; output capture pending"

    await add_output_artifact(panel_client, test_job["id"])
    terminal_job = await panel_client.app["db"].get_job(test_job["id"])
    await panel_client.app["jobs"]._apply_history(terminal_job, history_entry)

    passed = await (await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)).json()
    runtime = passed["definition"]["manifest"]["preflight"]["runtime"]
    assert passed["revision"] == revision
    assert runtime["status"] == "PASS"
    assert runtime["message"] == "Runtime execution passed"
    assert isinstance(runtime["tested_at"], float)

    presets = await (await panel_client.get("/api/presets", headers=LOGIN)).json()
    public = next(item for item in presets["items"] if item["id"] == workflow_id)
    assert public["preflight"]["runtime"]["status"] == "PASS"

    fail_response = await panel_client.post(
        f"/api/workflows/{workflow_id}/test",
        json={"positive_prompt": "runtime fail", "steps": 10},
        headers=LOGIN,
    )
    assert fail_response.status == 201, await fail_response.text()
    fail_job = await fail_response.json()
    await panel_client.app["jobs"].handle_ws_event({
        "type": "execution_error",
        "data": {"prompt_id": fail_job["id"], "exception_message": "fixture runtime boom"},
    })

    failed = await (await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)).json()
    runtime = failed["definition"]["manifest"]["preflight"]["runtime"]
    assert failed["revision"] == revision
    assert runtime["status"] == "FAIL"
    assert runtime["message"] == "Runtime execution failed"
    assert runtime["details"] == ["fixture runtime boom"]


@pytest.mark.asyncio
async def test_old_job_runtime_result_does_not_overwrite_new_revision(panel_client, comfy_server):
    workflow_id = await create_generic_workflow(panel_client)
    first = await (await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)).json()
    first_revision = first["revision"]

    test_response = await panel_client.post(
        f"/api/workflows/{workflow_id}/test",
        json={"positive_prompt": "old revision", "steps": 10},
        headers=LOGIN,
    )
    old_job = await test_response.json()
    assert old_job["workflow_revision"] == first_revision

    new_config = remote_config()
    new_config["name"] = "Standard SaveImage r2"
    saved = await panel_client.post(
        "/api/workflows",
        json={"workflow": save_image_workflow(), "config": new_config},
        headers=LOGIN,
    )
    assert saved.status == 201, await saved.text()
    second = await saved.json()
    assert second["revision"] > first_revision
    enabled = await panel_client.post(
        f"/api/workflows/{workflow_id}/status",
        json={"status": "enabled"},
        headers=LOGIN,
    )
    assert enabled.status == 200

    await add_output_artifact(panel_client, old_job["id"])
    panel_client.app["comfy"].history = AsyncMock(return_value={
        old_job["id"]: {
            "status": {"completed": True, "status_str": "success", "messages": []},
            "outputs": {},
        }
    })
    await panel_client.app["jobs"].handle_ws_event({
        "type": "execution_success",
        "data": {"prompt_id": old_job["id"]},
    })

    latest = await (await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)).json()
    assert latest["revision"] == second["revision"]
    assert latest["definition"]["manifest"]["preflight"]["runtime"]["status"] == "WARN"

    old = await panel_client.app["db"].get_workflow(workflow_id, first_revision)
    assert old["definition"]["manifest"]["preflight"]["runtime"]["status"] == "PASS"
