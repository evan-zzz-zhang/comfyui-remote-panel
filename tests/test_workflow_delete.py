import pytest

from test_app import LOGIN, comfy_server, panel_client
from test_workflow_config import remote_config, save_image_workflow


@pytest.mark.asyncio
async def test_custom_workflow_delete_is_immediate(panel_client):
    created = await panel_client.post(
        "/api/workflows",
        headers={**LOGIN, "Content-Type": "application/json"},
        json={"workflow": save_image_workflow(), "config": remote_config()},
    )
    assert created.status == 201, await created.text()
    workflow_id = (await created.json())["id"]

    enabled = await panel_client.post(
        f"/api/workflows/{workflow_id}/status",
        headers={**LOGIN, "Content-Type": "application/json"},
        json={"status": "enabled"},
    )
    assert enabled.status == 200, await enabled.text()

    before = await panel_client.get("/api/presets", headers=LOGIN)
    assert workflow_id in {item["id"] for item in (await before.json())["items"]}

    deleted = await panel_client.delete(f"/api/workflows/{workflow_id}", headers=LOGIN)
    assert deleted.status == 204, await deleted.text()

    workflows = await panel_client.get("/api/workflows", headers=LOGIN)
    assert workflow_id not in {item["id"] for item in (await workflows.json())["items"]}

    presets = await panel_client.get("/api/presets", headers=LOGIN)
    assert workflow_id not in {item["id"] for item in (await presets.json())["items"]}

    detail = await panel_client.get(f"/api/workflows/{workflow_id}", headers=LOGIN)
    assert detail.status == 404


@pytest.mark.asyncio
async def test_builtin_workflow_cannot_be_deleted(panel_client):
    response = await panel_client.delete("/api/workflows/h3-fl2va-v4step600", headers=LOGIN)
    assert response.status == 409
    assert (await response.json())["error"]["code"] == "builtin_workflow"
