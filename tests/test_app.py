from __future__ import annotations

import asyncio
import json
import io
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import FormData, web
from PIL import Image

from comfyui_remote_panel.app import _write_sse, create_app
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.jobs import safe_summary
from test_workflow_config import remote_config, save_image_workflow


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}


@pytest.fixture
async def comfy_server(aiohttp_server):
    app = web.Application()
    app["submitted"] = []
    app["cancelled"] = []
    app["queue_running"] = []
    app["queue_pending"] = []

    async def stats(_):
        return web.json_response({"system": {"comfyui_version": "0.30.0"}, "devices": []})

    async def queue(_):
        return web.json_response({"queue_running": app["queue_running"], "queue_pending": app["queue_pending"]})

    async def object_info(request):
        node = request.match_info["node"]
        return web.json_response({node: {"input": {}}})

    model_values = {
        "diffusion_models": [r"MiniMax-H3\minimax_h3_fl2va_pruned_int8_convrot.safetensors", r"MiniMax-H3\minimax_h3_ref2va_pruned_int8_convrot.safetensors"],
        "text_encoders": [r"MiniMax-H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors"],
        "vae": ["minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
        "loras": ["minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors", "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"],
    }

    async def models(request):
        return web.json_response(model_values.get(request.match_info["category"], []))

    async def submit(request):
        body = await request.json()
        app["submitted"].append(body)
        return web.json_response({"prompt_id": body["prompt_id"], "number": 1, "node_errors": {}})

    async def history(request):
        return web.json_response({})

    async def cancel(request):
        known = any(item["prompt_id"] == request.match_info["job_id"] for item in app["submitted"])
        if known:
            app["cancelled"].append(request.match_info["job_id"])
        return web.json_response({"cancelled": known})

    app.router.add_get("/system_stats", stats)
    app.router.add_get("/queue", queue)
    app.router.add_get("/object_info/{node}", object_info)
    app.router.add_get("/models/{category}", models)
    app.router.add_post("/prompt", submit)
    app.router.add_get("/history/{job_id}", history)
    app.router.add_post("/api/jobs/{job_id}/cancel", cancel)
    return await aiohttp_server(app)


@pytest.fixture
async def panel_client(tmp_path, comfy_server, aiohttp_client):
    config = Config(
        host="127.0.0.1", port=8190, public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",), comfyui_base_url=str(comfy_server.make_url("/")).rstrip("/"),
        comfyui_input_dir=tmp_path / "comfy-input", comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0", data_dir=tmp_path / "data", workflow_dir=ROOT / "workflows",
        monitoring_interval=60, nvidia_smi_timeout=.1,
    )
    return await aiohttp_client(create_app(config))


@pytest.mark.asyncio
async def test_health_is_only_anonymous_route(panel_client):
    response = await panel_client.get("/healthz")
    assert response.status == 200
    assert await response.json() == {"status": "ok"}
    assert (await panel_client.get("/")).status == 403
    authorized = await panel_client.get("/", headers=LOGIN)
    assert authorized.status == 200
    assert "frame-ancestors 'none'" in authorized.headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in authorized.headers


@pytest.mark.asyncio
async def test_panel_opens_when_comfyui_is_offline(tmp_path, aiohttp_client):
    config = Config(
        host="127.0.0.1", port=8190, public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",), comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "comfy-input", comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0", data_dir=tmp_path / "data", workflow_dir=ROOT / "workflows",
        monitoring_interval=60, nvidia_smi_timeout=.1,
    )
    client = await aiohttp_client(create_app(config))

    response = await client.get("/", headers=LOGIN)
    assert response.status == 200
    html = await response.text()
    assert "Comfy Remote" in html
    assert "H3 生成台" not in html

    presets = await client.get("/api/presets", headers=LOGIN)
    assert presets.status == 200


@pytest.mark.asyncio
async def test_wrong_identity_and_cross_origin_write_are_rejected(panel_client):
    assert (await panel_client.get("/api/jobs", headers={"Tailscale-User-Login": "other@example.com"})).status == 403
    headers = {**LOGIN, "Origin": "https://evil.example"}
    assert (await panel_client.post("/api/jobs", headers=headers)).status == 403


@pytest.mark.asyncio
async def test_comfyui_control_requires_confirmation_and_fixed_action(panel_client):
    endpoint = "/api/comfyui/control/restart"
    assert (await panel_client.post(endpoint, headers=LOGIN)).status == 400
    panel_client.app["lifecycle"].trigger = AsyncMock(return_value={"enabled": True, "operation": "restart"})
    response = await panel_client.post(
        endpoint,
        json={"confirm": True},
        headers=LOGIN,
    )
    assert response.status == 202
    panel_client.app["lifecycle"].trigger.assert_awaited_once_with("restart")


@pytest.mark.asyncio
async def test_create_uses_same_panel_and_prompt_id(panel_client, comfy_server):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "一个缓慢推进的镜头")
    form.add_field("duration_seconds", "5")
    form.add_field("aspect_ratio", "9:16")
    form.add_field("megapixels", "0.4")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    assert isinstance(job["seed"], str)
    submitted = comfy_server.app["submitted"][-1]
    assert submitted["prompt_id"] == job["id"]
    assert submitted["prompt"]["127"]["inputs"]["unet_name"] == r"MiniMax-H3\minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    assert submitted["prompt"]["128"]["inputs"]["clip_name"] == r"MiniMax-H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
    assert submitted["prompt"]["156"]["inputs"] == {}
    assert submitted["prompt"]["136"]["inputs"]["first_frame"] == ["156", 0]
    assert submitted["prompt"]["136"]["inputs"]["last_frame"] == ["156", 1]


@pytest.mark.asyncio
async def test_fl2va_standardizer_rejects_empty_prompt_with_image(panel_client, comfy_server):
    image_data = io.BytesIO()
    Image.new("RGB", (24, 12), "red").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-fl2va")
    form.add_field("prompt", "")
    form.add_field("first_frame", image_data.getvalue(), filename="first.png", content_type="image/png")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 400
    assert "提示词不能为空" in (await response.json())["error"]["message"]
    assert not comfy_server.app["submitted"]


@pytest.mark.asyncio
async def test_fl2va_image_submission_allows_empty_prompt_when_standardizer_disabled(panel_client, comfy_server):
    image_data = io.BytesIO()
    Image.new("RGB", (24, 12), "red").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-fl2va")
    form.add_field("prompt", "")
    form.add_field("values_json", json.dumps({
        "generation_mode": "v4_600step",
        "prompt_standardization": False,
    }))
    form.add_field("first_frame", image_data.getvalue(), filename="first.png", content_type="image/png")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    assert job["status"] == "queued"
    assert job["generation_mode"] == "v4_600step"
    graph = comfy_server.app["submitted"][-1]["prompt"]
    assert graph["156"]["inputs"]["first_frame"] == ["9001", 0]
    assert graph["136"]["inputs"]["first_frame"] == ["156", 0]
    assert graph["138"]["inputs"]["value"] == ""
    assert graph["154"]["inputs"]["switch"] is False


@pytest.mark.asyncio
async def test_submission_response_error_does_not_mark_accepted_prompt_failed(panel_client, comfy_server):
    async def submit(prompt_id, _prompt):
        comfy_server.app["queue_pending"][:] = [[1, prompt_id]]
        raise RuntimeError("response was lost after enqueue")

    panel_client.app["comfy"].submit = submit
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "响应异常但已入队")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    assert job["status"] == "queued"
    assert job["error_summary"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", [2**53 - 1, 2**53 + 1])
async def test_seed_json_contract_preserves_browser_boundary_values(panel_client, seed):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试 seed JSON 契约")
    form.add_field("seed", str(seed))
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)

    assert response.status == 201
    assert (await response.json())["seed"] == str(seed)


@pytest.mark.asyncio
async def test_reference_aspect_without_image_is_rejected_before_submission(panel_client, comfy_server):
    before = len(comfy_server.app["submitted"])
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "reference ratio requires an image")
    form.add_field("aspect_ratio", "reference")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 400
    assert "参考图" in (await response.json())["error"]["message"]
    assert len(comfy_server.app["submitted"]) == before


@pytest.mark.asyncio
async def test_ref2va_accepts_multiple_images_video_and_audio(panel_client, comfy_server):
    image_data = io.BytesIO()
    Image.new("RGB", (24, 12), "red").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-ref2va-v4step600")
    form.add_field("prompt", "<Picture 1> follows <Video 1> with <Audio 2>")
    form.add_field("ref_images", image_data.getvalue(), filename="one.fake", content_type="application/octet-stream")
    form.add_field("ref_images", image_data.getvalue(), filename="two.png", content_type="image/png")
    form.add_field("ref_videos", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32, filename="clip.bin", content_type="application/octet-stream")
    form.add_field("ref_audios", b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32, filename="sound.bin", content_type="application/octet-stream")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    assert job["media_counts"] == {"image": 2, "video": 1, "audio": 1}
    graph = comfy_server.app["submitted"][-1]["prompt"]
    target = graph["136"]["inputs"]
    assert target["ref_images.ref_image_0"] == ["9100", 0]
    assert target["ref_images.ref_image_1"] == ["9101", 0]
    assert target["ref_videos.ref_video_0"] == ["9300", 0]
    assert target["ref_video_audios.ref_video_audio_0"] == ["9300", 1]
    assert target["ref_audios.ref_audio_0"] == ["9400", 0]
    storage_key = panel_client.app["files"].storage_key(job["id"])
    assert graph["9200"] == {"class_type": "LoadVideo", "inputs": {"file": f"h3_remote/{storage_key}_video-0.mp4"}}
    assert graph["9400"]["class_type"] == "LoadAudio"

    await panel_client.app["db"].update_job(job["id"], status="failed")
    draft_response = await panel_client.post(f"/api/jobs/{job['id']}/retry", headers=LOGIN)
    draft = await draft_response.json()
    retry_form = FormData(default_to_multipart=True)
    for field in ("preset_id", "prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps", "retry_source_id"):
        retry_form.add_field(field, str(draft[field]))
    retry_response = await panel_client.post("/api/jobs", data=retry_form, headers=LOGIN)
    assert retry_response.status == 201, await retry_response.text()
    retried = await retry_response.json()
    assert retried["media_counts"] == {"image": 2, "video": 1, "audio": 1}
    retried_graph = comfy_server.app["submitted"][-1]["prompt"]
    retried_key = panel_client.app["files"].storage_key(retried["id"])
    assert retried_graph["9200"]["inputs"]["file"] == f"h3_remote/{retried_key}_video-0.mp4"


@pytest.mark.asyncio
async def test_ref2va_retry_can_delete_and_replace_one_slot(panel_client, comfy_server):
    image_data = io.BytesIO()
    Image.new("RGB", (24, 12), "blue").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-ref2va-v4step600")
    form.add_field("prompt", "slot test")
    form.add_field("ref_images", image_data.getvalue(), filename="one.png", content_type="image/png")
    form.add_field("ref_images", image_data.getvalue(), filename="two.png", content_type="image/png")
    form.add_field("ref_videos", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32, filename="clip.mp4", content_type="video/mp4")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    original = await response.json()
    await panel_client.app["db"].update_job(original["id"], status="failed")
    draft = await (await panel_client.post(f"/api/jobs/{original['id']}/retry", headers=LOGIN)).json()

    retry_form = FormData(default_to_multipart=True)
    for field in ("preset_id", "prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps", "retry_source_id"):
        retry_form.add_field(field, str(draft[field]))
    retry_form.add_field("retry_keep_roles", json.dumps(["image_0"]))
    retry_form.add_field("image_1", image_data.getvalue(), filename="replacement.png", content_type="image/png")
    retried_response = await panel_client.post("/api/jobs", data=retry_form, headers=LOGIN)
    assert retried_response.status == 201, await retried_response.text()
    retried = await retried_response.json()
    assert retried["media_counts"] == {"image": 2, "video": 0, "audio": 0}
    target = comfy_server.app["submitted"][-1]["prompt"]["136"]["inputs"]
    assert target["ref_images.ref_image_0"] == ["9100", 0]
    assert target["ref_images.ref_image_1"] == ["9101", 0]
    assert "ref_videos.ref_video_0" not in target


@pytest.mark.asyncio
async def test_job_progress_is_folded_across_workflow_phases(panel_client):
    job_id = "00000000-0000-0000-0000-000000000003"
    await panel_client.app["db"].create_job({
        "id": job_id, "preset_id": "h3-fl2va-v4step600", "status": "queued", "mode": "纯文字",
        "prompt": "progress", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": .4, "seed": 1,
    }, [])
    jobs = panel_client.app["jobs"]
    await jobs.handle_ws_event({"type": "execution_start", "data": {"prompt_id": job_id, "node": "125"}})
    await jobs.handle_ws_event({"type": "progress", "data": {"prompt_id": job_id, "value": 50, "max": 100}})
    sampling = jobs.public_job(await panel_client.app["db"].get_job(job_id))
    assert sampling["progress_phase"] == "sampling"
    assert sampling["progress_percent"] == 40
    await jobs.handle_ws_event({"type": "execution_start", "data": {"prompt_id": job_id, "node": "122"}})
    decoding = jobs.public_job(await panel_client.app["db"].get_job(job_id))
    assert decoding["progress_phase"] == "decode"
    assert decoding["progress_percent"] == 78


@pytest.mark.asyncio
async def test_new_comfy_progress_state_updates_job_progress(panel_client):
    job_id = "00000000-0000-0000-0000-000000000004"
    await panel_client.app["db"].create_job({
        "id": job_id, "preset_id": "h3-fl2va-v4step600", "status": "queued", "mode": "纯文字",
        "prompt": "progress state", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": .4, "seed": 1,
    }, [])
    await panel_client.app["jobs"].handle_ws_event({
        "type": "progress_state",
        "data": {
            "prompt_id": job_id,
            "nodes": {
                "125": {
                    "state": "running", "value": 3, "max": 8,
                    "node_id": "125", "display_node_id": "125",
                },
            },
        },
    })
    job = panel_client.app["jobs"].public_job(await panel_client.app["db"].get_job(job_id))
    assert job["status"] == "running"
    assert job["stage"] == "采样"
    assert job["progress_value"] == 3
    assert job["progress_max"] == 8
    assert job["progress_percent"] == 33


@pytest.mark.asyncio
async def test_cancel_targets_only_requested_job(panel_client, comfy_server):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试定向取消")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    job = await response.json()
    cancelled = await panel_client.post(f"/api/jobs/{job['id']}/cancel", headers=LOGIN)
    assert cancelled.status == 200
    assert (await cancelled.json())["status"] == "cancelled"
    assert comfy_server.app["cancelled"] == [job["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("submit_fails", [False, True])
async def test_cancelled_submission_cannot_return_to_queued_or_failed(panel_client, submit_fails):
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_submit(*_args, **_kwargs):
        started.set()
        await release.wait()
        if submit_fails:
            raise RuntimeError("late submission result")
        return {"prompt_id": _args[0]}

    panel_client.app["comfy"].submit = delayed_submit
    panel_client.app["comfy"].cancel = AsyncMock(return_value=True)
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试提交与取消竞态")
    create_task = asyncio.create_task(panel_client.post("/api/jobs", data=form, headers=LOGIN))

    await asyncio.wait_for(started.wait(), timeout=2)
    [submitting] = await panel_client.app["db"].active_jobs()
    cancelled = await panel_client.post(f"/api/jobs/{submitting['id']}/cancel", headers=LOGIN)
    assert (await cancelled.json())["status"] == "cancelled"

    release.set()
    created = await create_task
    assert created.status == 201
    assert (await created.json())["status"] == "cancelled"
    assert (await panel_client.app["db"].get_job(submitting["id"]))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_queue_position_includes_non_panel_jobs(panel_client, comfy_server):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试完整队列位置")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    job = await response.json()
    comfy_server.app["queue_pending"].extend([[1, "external-job"], [2, job["id"]]])
    await panel_client.app["jobs"].reconcile_once()
    assert (await panel_client.app["db"].get_job(job["id"]))["queue_position"] == 2


@pytest.mark.asyncio
async def test_websocket_terminal_state_wins_over_delayed_reconcile(panel_client):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试 reconcile 与 WebSocket 竞态")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    job = await response.json()

    history_started = asyncio.Event()
    release_history = asyncio.Event()

    async def empty_queue():
        return {"queue_running": [], "queue_pending": []}

    async def delayed_history(_job_id):
        history_started.set()
        await release_history.wait()
        return {_job_id: {"status": {"completed": True, "status_str": "success"}, "outputs": {}}}

    panel_client.app["comfy"].queue = empty_queue
    panel_client.app["comfy"].history = delayed_history
    reconcile = asyncio.create_task(panel_client.app["jobs"].reconcile_once())
    await asyncio.wait_for(history_started.wait(), timeout=2)

    await panel_client.app["jobs"].handle_ws_event({
        "type": "execution_error",
        "data": {"prompt_id": job["id"], "exception_message": "deterministic failure"},
    })
    release_history.set()
    await reconcile

    current = await panel_client.app["db"].get_job(job["id"])
    assert current["status"] == "failed"
    assert current["error_summary"] == "deterministic failure"


@pytest.mark.asyncio
async def test_missing_upstream_requires_persisted_grace_confirmation(panel_client):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试暂时找不到上游任务")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    job = await response.json()

    await panel_client.app["jobs"].reconcile_once()
    current = await panel_client.app["db"].get_job(job["id"])
    assert current["status"] == "queued"
    assert current["missing_observations"] == 1

    await panel_client.app["db"].update_job(
        job["id"], missing_observations=2, missing_first_at=time.time() - 31
    )
    await panel_client.app["jobs"].reconcile_once()
    current = await panel_client.app["db"].get_job(job["id"])
    assert current["status"] == "interrupted"
    assert current["error_code"] == "missing_upstream"


@pytest.mark.asyncio
async def test_unrequested_execution_interruption_is_not_user_cancellation(panel_client):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试异常中断语义")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    job = await response.json()

    await panel_client.app["jobs"].handle_ws_event({
        "type": "execution_interrupted",
        "data": {"prompt_id": job["id"]},
    })
    current = await panel_client.app["db"].get_job(job["id"])
    assert current["status"] == "interrupted"
    assert current["error_code"] == "execution_interrupted"


@pytest.mark.asyncio
async def test_prompt_has_independent_streaming_limit(panel_client):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "字" * 11_000)
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 413
    assert (await response.json())["error"]["code"] == "field_too_large"


@pytest.mark.asyncio
async def test_missing_output_recovery_has_terminal_limit(panel_client):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试输出恢复上限")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    job = await response.json()
    await panel_client.app["db"].update_job(
        job["id"], status="succeeded", finished_at=time.time() - 25 * 60 * 60,
    )
    panel_client.app["comfy"].history = AsyncMock(return_value={})

    await panel_client.app["jobs"]._recover_missing_outputs()
    current = await panel_client.app["db"].get_job(job["id"])
    assert current["status"] == "output_missing"
    assert current["recovery_attempts"] == 1


@pytest.mark.asyncio
async def test_retry_returns_draft_then_user_submits_new_job(panel_client, comfy_server):
    form = FormData(default_to_multipart=True)
    form.add_field("prompt", "测试重试")
    form.add_field("seed", "18446744073709551615")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    original = await response.json()
    detail = await panel_client.get(f"/api/jobs/{original['id']}", headers=LOGIN)
    listed = await panel_client.get("/api/jobs", headers=LOGIN)
    assert (await detail.json())["seed"] == str(2**64 - 1)
    assert (await listed.json())["items"][0]["seed"] == str(2**64 - 1)
    stream = Mock(write=AsyncMock())
    await _write_sse(stream, "job", original)
    event_payload = stream.write.await_args.args[0].decode("utf-8")
    assert json.loads(event_payload.split("data: ", 1)[1])["seed"] == str(2**64 - 1)
    await panel_client.app["db"].update_job(original["id"], status="failed")
    response = await panel_client.post(f"/api/jobs/{original['id']}/retry", headers=LOGIN)
    draft = await response.json()
    assert response.status == 200
    assert draft["retry_source_id"] == original["id"]
    assert draft["seed"] == original["seed"] == str(2**64 - 1)
    assert len(comfy_server.app["submitted"]) == 1

    retry_form = FormData(default_to_multipart=True)
    for field in ("preset_id", "prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps", "retry_source_id"):
        retry_form.add_field(field, str(draft[field]))
    response = await panel_client.post("/api/jobs", data=retry_form, headers=LOGIN)
    retried = await response.json()
    assert response.status == 201
    assert retried["id"] != original["id"]
    assert retried["seed"] == original["seed"]
    assert comfy_server.app["submitted"][-1]["prompt_id"] == retried["id"]


@pytest.mark.asyncio
async def test_video_single_range(panel_client):
    db = panel_client.app["db"]
    files = panel_client.app["files"]
    job_id = "00000000-0000-0000-0000-000000000001"
    await db.create_job({
        "id": job_id, "preset_id": "h3-fl2va-v4step600", "status": "succeeded", "mode": "纯文字",
        "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": .4, "seed": 1,
    }, [])
    path = files.output_root / "video.mp4"
    path.write_bytes(b"0123456789")
    await db.add_file(job_id, "output", path, 10)
    response = await panel_client.get(f"/api/jobs/{job_id}/video", headers={**LOGIN, "Range": "bytes=2-5"})
    assert response.status == 206
    assert response.headers["Content-Range"] == "bytes 2-5/10"
    assert await response.read() == b"2345"
    invalid = await panel_client.get(f"/api/jobs/{job_id}/video", headers={**LOGIN, "Range": "bytes=99-100"})
    assert invalid.status == 416
    assert invalid.headers["Content-Range"] == "bytes */10"
    download = await panel_client.get(f"/api/jobs/{job_id}/video?download=1", headers=LOGIN)
    assert download.status == 200
    assert download.headers["Content-Disposition"].startswith('attachment; filename="h3-fl2va-v4step600-')
    assert download.headers["Content-Disposition"].endswith('-000000.mp4"')


@pytest.mark.asyncio
async def test_save_video_images_descriptor_is_captured(panel_client):
    db = panel_client.app["db"]
    files = panel_client.app["files"]
    job_id = "00000000-0000-0000-0000-000000000002"
    await db.create_job({
        "id": job_id, "preset_id": "h3-fl2va-v4step600", "status": "succeeded", "mode": "纯文字",
        "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": .4, "seed": 1,
    }, [])
    path = files.output_root / f"{files.storage_key(job_id)}_00001_.mp4"
    path.write_bytes(b"video")
    captured = await panel_client.app["jobs"]._capture_output(job_id, {
        "outputs": {"92": {"images": [{
            "filename": path.name, "subfolder": "h3_remote", "type": "output",
        }], "animated": [True]}},
    })
    assert captured is True
    assert (await db.get_job(job_id))["has_video"] is True


@pytest.mark.asyncio
async def test_delete_hides_history_and_purge_is_explicit(panel_client):
    db = panel_client.app["db"]
    files = panel_client.app["files"]
    job_id = "00000000-0000-0000-0000-000000000003"
    path = files.output_root / files.flat_output_name(job_id)
    path.write_bytes(b"video")
    await db.create_job({
        "id": job_id, "preset_id": "h3-fl2va-v4step600", "status": "succeeded", "mode": "纯文字",
        "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": .4, "seed": 1,
    }, [{"role": "output", "path": path, "size_bytes": 5}])

    hidden = await panel_client.delete(f"/api/jobs/{job_id}", json={"confirm": True}, headers=LOGIN)

    assert hidden.status == 204
    assert path.exists()
    assert (await db.get_job(job_id))["status"] == "hidden"
    assert all(item["id"] != job_id for item in (await db.list_jobs())["items"])

    purged = await panel_client.post(f"/api/jobs/{job_id}/purge", json={"confirm": True}, headers=LOGIN)

    assert purged.status == 204
    assert not path.exists()
    assert await db.get_job(job_id) is None


@pytest.mark.asyncio
async def test_generic_saveimage_workflow_crud_submit_and_artifact(panel_client, comfy_server):
    created = await panel_client.post(
        "/api/workflows", headers={**LOGIN, "Content-Type": "application/json"},
        json={"workflow": save_image_workflow(), "config": remote_config()},
    )
    assert created.status == 201, await created.text()
    assert (await created.json())["status"] == "draft"

    enabled = await panel_client.post(
        "/api/workflows/standard-save-image/status", headers={**LOGIN, "Content-Type": "application/json"},
        json={"status": "enabled"},
    )
    assert enabled.status == 200, await enabled.text()

    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "standard-save-image")
    form.add_field("values_json", json.dumps({"positive_prompt": "A generic dog", "steps": 11}))
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    submitted = comfy_server.app["submitted"][-1]["prompt"]
    assert submitted["2"]["inputs"]["text"] == "A generic dog"
    assert submitted["4"]["inputs"]["steps"] == 11

    output_name = f"{panel_client.app['files'].storage_key(job['id'])}_00001_.png"
    output_path = panel_client.app["files"].output_root / output_name
    output_path.write_bytes(b"png-result")
    captured = await panel_client.app["jobs"]._capture_output(job["id"], {
        "outputs": {"6": {"images": [{"filename": output_name, "subfolder": "h3_remote", "type": "output"}]}}
    })
    assert captured is True
    response = await panel_client.get(f"/api/jobs/{job['id']}/artifacts", headers=LOGIN)
    [artifact] = (await response.json())["items"]
    assert artifact["kind"] == "image"
    downloaded = await panel_client.get(f"/api/jobs/{job['id']}/artifacts/{artifact['id']}", headers=LOGIN)
    assert downloaded.status == 200
    assert await downloaded.read() == b"png-result"


def test_error_summary_removes_local_paths_and_addresses():
    separator = chr(92)
    local_path = "D:" + separator + separator.join(("AI", "ComfyUI", "models", "secret.safetensors"))
    summary = safe_summary(f"failed at {local_path} via 127.0.0.1:8188")
    assert local_path not in summary
    assert "127.0.0.1" not in summary
    assert "[本机路径]" in summary
    assert "[本机地址]" in summary
