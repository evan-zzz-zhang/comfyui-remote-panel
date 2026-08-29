from __future__ import annotations

from pathlib import Path

import pytest

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"
JS = (STATIC / "v041_ui.js").read_text(encoding="utf-8")
CSS = (STATIC / "v041.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.0.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )


def test_retained_preview_uses_server_identity_without_fake_files():
    assert "/api/jobs/${encodeURIComponent(item.sourceJob)}/inputs/${encodeURIComponent(item.artifact_id)}" in JS
    assert "retained_media" in JS
    assert 'formData.set("retry_keep_roles", JSON.stringify(retainedKeepRoles()))' in JS
    assert "new File(" not in JS
    assert "new Blob(" not in JS
    assert ".blob()" not in JS
    assert "formData.append(" not in JS


def test_retained_images_use_native_lazy_loading_without_new_observers():
    assert 'image.loading = "lazy"' in JS
    assert 'image.decoding = "async"' in JS
    assert "MutationObserver" not in JS
    assert "IntersectionObserver" not in JS


def test_output_metadata_replaces_compact_job_meta_size():
    assert 'item.direction === "output" && item.kind === "image"' in JS
    assert "artifact?.metadata" in JS
    assert "`${width}×${height} · ${format} · ${formatBytes(artifact.size_bytes)}`" in JS
    assert 'spans.at(-1)' in JS
    assert 'target.dataset.v041OutputMetadata = "1"' in JS


def test_v041_patch_does_not_rewrite_protected_prompt_or_settings_markup():
    assert "prompt-field" not in JS
    assert "settings-close" not in JS
    assert "nav-workflows" not in JS
    assert '<label class="creation-section prompt-field">' in INDEX
    assert 'id="settings-close"' in INDEX
    assert 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z' in INDEX
    assert "v041_ui.js" not in INDEX
    assert "v041.css" not in INDEX
    assert set(line.strip().split(" ", 1)[0] for line in CSS.splitlines() if line.strip() and not line.lstrip().startswith((".", "}"))) <= {
        "position:", "top:", "right:", "z-index:", "min-height:", "padding:", "border:",
        "border-radius:", "background:", "color:", "font:", "font-size:", "cursor:",
        "display:", "align-items:", "justify-content:",
    }


@pytest.mark.asyncio
async def test_root_loads_v041_assets_after_auth_without_source_index_rewrite(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    assert (await client.get("/")).status == 403
    response = await client.get("/", headers={"Tailscale-User-Login": "owner@example.com"})
    assert response.status == 200
    html = await response.text()
    assert '<link rel="stylesheet" href="/static/v041.css?v=0.4.1">' in html
    assert '<script src="/static/v041_ui.js?v=0.4.1" defer></script>' in html
    assert '<label class="creation-section prompt-field">' in html
    assert 'id="settings-close"' in html
