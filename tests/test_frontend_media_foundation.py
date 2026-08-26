from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_generic_image_preview_reuses_upload_card_foundation() -> None:
    runtime = _read("configurator_v2_runtime.js")
    app = _read("app.js")
    css = _read("configurator_v2.css")

    # H3 already uses upload-card for single-image preview; generic workflows must
    # join the same structural/CSS contract instead of inventing a third preview.
    assert '.upload-card input' in app
    assert 'window.ComfyRemoteMediaUI' in runtime
    assert 'card.classList.add("upload-card")' in runtime
    assert 'URL.revokeObjectURL' in runtime
    assert '.generic-reference-card.upload-card' in css

    assert 'generic-source-preview' not in runtime
    assert 'has-source-preview' not in runtime
    assert 'MutationObserver' not in runtime
    assert 'document.createElement("style")' not in runtime


def test_single_image_results_use_centered_single_item_layout() -> None:
    css = _read("configurator_v2.css")

    assert '.artifact-preview.one .artifact-preview-item{display:grid;place-items:center}' in css
    assert '.artifact-grid.gallery:has(>.artifact-item:only-child)' in css
    assert 'max-height:calc(100dvh - 150px)' in css
    assert 'object-fit:contain' in css
