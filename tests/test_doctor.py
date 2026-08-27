from pathlib import Path
from types import SimpleNamespace

import pytest

from comfyui_remote_panel.db import Database
from comfyui_remote_panel.doctor import (
    DoctorCheck,
    FAIL,
    PASS,
    WARN,
    format_markdown,
    redact_text,
    workflow_compatibility_detail,
)
from comfyui_remote_panel.doctor_workflows import load_doctor_presets
from comfyui_remote_panel.preset import Preset
from comfyui_remote_panel.workflow_config import build_definition
from test_workflow_config import remote_config, save_image_workflow


def test_doctor_report_redacts_user_paths_email_tailscale_and_secret():
    windows_user_path = "C:" + "\\Users\\" + "Alice\\ComfyUI"
    source = (
        windows_user_path
        + " owner@example.com machine.tail123.ts.net token=super-secret"
    )
    redacted = redact_text(source)
    assert "Alice" not in redacted
    assert "owner@example.com" not in redacted
    assert "machine.tail123.ts.net" not in redacted
    assert "super-secret" not in redacted
    assert "<USER_PATH>" in redacted
    assert "o***@example.com" in redacted
    assert "<TAILSCALE_HOST>.ts.net" in redacted
    assert "<REDACTED>" in redacted


def test_markdown_report_redacts_absolute_paths_on_non_system_drives():
    report = format_markdown(
        [
            DoctorCheck("Core", "config.toml", PASS, r"G:\AI-project\comfyui-remote-panel\config.toml"),
            DoctorCheck("Core", "data directory", PASS, r"G:\AI-project\comfyui-remote-panel\data (writable)"),
            DoctorCheck("ComfyUI", "input directory", PASS, r"G:\AI\ComfyUI_H3_Portable\ComfyUI\input (writable)"),
            DoctorCheck("ComfyUI", "output directory", PASS, r"G:\AI\ComfyUI_H3_Portable\ComfyUI\output (readable)"),
        ]
    )
    assert "G:\\" not in report
    assert "AI-project" not in report
    assert "ComfyUI_H3_Portable" not in report
    assert report.count("<PATH>") >= 4
    assert "(writable)" in report
    assert "(readable)" in report


def test_markdown_report_uses_only_public_severity_levels():
    report = format_markdown(
        [
            DoctorCheck("Core", "Python", PASS, "3.13"),
            DoctorCheck("Remote access", "Tailscale", WARN, "not installed"),
            DoctorCheck("ComfyUI", "API", FAIL, "offline"),
        ]
    )
    assert "**PASS**" in report
    assert "**WARN**" in report
    assert "**FAIL**" in report
    assert "NOT READY" in report


def test_workflow_compatibility_detail_is_profile_only_and_never_dumps_workflow_json():
    manifest = {
        "id": "wai-img2img",
        "name": "WAI img2img",
        "minimum_comfyui_version": "0.26.0",
        "output_bindings": [{"node": "8", "kind": "image", "primary": True}],
        "input_bindings": {"media": {"type": "slots", "slots": {
            "image_0": {"kind": "image", "required": True, "ui": {"label": "源图", "optional": False}},
        }}},
        "parameters": {},
        "dependencies": [],
        "capability_profile": {
            "output_type": "image",
            "required_media_inputs": {"image": 1},
        },
        "preflight": {
            "parameters": {"status": "WARN", "message": "batch controlled by workflow"},
        },
    }
    preset = Preset(Path("."), manifest, {"8": {"class_type": "SaveImage", "inputs": {"secret_workflow_value": "DO_NOT_PRINT"}}})
    detail = workflow_compatibility_detail(preset, ["缺少节点：FooNode"])
    assert "output=image" in detail
    assert "required inputs=image×1" in detail
    assert "missing nodes=FooNode" in detail
    assert "batch controlled by workflow" in detail
    assert "DO_NOT_PRINT" not in detail
    assert "secret_workflow_value" not in detail


@pytest.mark.asyncio
async def test_doctor_loads_latest_persisted_nonbuiltin_workflows(tmp_path):
    database_path = tmp_path / "data" / "panel.db"
    database = Database(database_path)
    await database.initialize()
    definition = build_definition(save_image_workflow(), remote_config())
    await database.save_workflow(definition, status="enabled")

    config = SimpleNamespace(
        workflow_dir=tmp_path / "workflows",
        database_path=database_path,
    )
    presets = await load_doctor_presets(config)
    assert "standard-save-image" in presets
    preset = presets["standard-save-image"]
    assert preset.manifest["name"] == "Standard SaveImage"
    assert preset.manifest["output_bindings"][0]["kind"] == "image"
