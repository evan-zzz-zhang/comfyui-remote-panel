from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module("h3_bundle_builder", ROOT / "scripts/build_h3_workflow_bundle.py")
downloader = load_module("h3_resource_downloader", ROOT / "h3-workflows/download_resources.py")


def test_all_native_graphs_match_runtime_contract():
    builder.validate()


def test_broken_visual_link_is_rejected():
    graph = json.loads((builder.BUNDLE / "comfyui/fl2va_original_raw.json").read_text(encoding="utf-8"))
    widgets = json.loads((builder.BUNDLE / "widget-map.json").read_text())
    graph["links"][0][4] += 1
    with pytest.raises(ValueError, match="Mismatched visual input link"):
        builder.graph_to_prompt(graph, widgets)


def test_release_archives_are_reproducible_and_source_allowlisted(tmp_path):
    first = builder.build(tmp_path / "first")
    second = builder.build(tmp_path / "second")
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]
    with zipfile.ZipFile(first[0]) as archive:
        names = archive.namelist()
        assert len([n for n in names if n.endswith("manifest.json")]) == 18
        assert len([n for n in names if n.endswith("workflow.json")]) == 18
    with zipfile.ZipFile(first[1]) as archive:
        assert len([n for n in archive.namelist() if n.startswith("comfyui/")]) == 18
    inventory = json.loads((builder.BUNDLE / "node-provenance.json").read_text())
    with zipfile.ZipFile(first[2]) as archive:
        actual = {n for n in archive.namelist() if n.startswith("custom_nodes/")}
        assert actual == {f"custom_nodes/{item['file']}" for item in inventory}
        assert not any("/skill/" in n or "/guides/" in n or "__pycache__" in n for n in actual)


def test_resource_download_verifies_normalized_content_and_rejects_tampering():
    expected = hashlib.sha256(b"official\nguide\n").hexdigest()
    assert downloader.verified_content(b"official\r\nguide\r\n", expected) == b"official\nguide\n"
    with pytest.raises(ValueError, match="checksum mismatch"):
        downloader.verified_content(b"changed guide", expected)


def test_resource_download_preserves_existing_modified_files(tmp_path):
    destination = tmp_path / "guide.txt"
    destination.write_text("local edits")
    (tmp_path / "resources.json").write_text(json.dumps([{
        "path": "guide.txt", "url": "https://example.com/unused",
        "sha256": hashlib.sha256(b"official").hexdigest(),
    }]))
    with pytest.raises(ValueError, match="checksum mismatch"):
        downloader.download(tmp_path)
    assert destination.read_text() == "local edits"


def test_node_import_preserves_other_extension_and_previous_process_cache(tmp_path, monkeypatch):
    folder_paths = ModuleType("folder_paths")
    folder_paths.get_temp_directory = lambda: str(tmp_path / "comfy-temp")
    monkeypatch.setitem(sys.modules, "folder_paths", folder_paths)
    monkeypatch.setitem(sys.modules, "av", ModuleType("av"))
    pil = ModuleType("PIL")
    for name in ("Image", "ImageDraw", "ImageFont", "ImageOps"):
        setattr(pil, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, "PIL", pil)
    source = builder.BUNDLE / "custom_nodes/ComfyRemoteH3PromptWriter/backend/media.py"
    # Fresh ComfyUI installs may not have a temp directory yet.
    first = load_module("h3_media_first", source)
    previous = first.CACHE_ROOT / "in-flight.txt"
    previous.write_text("keep")
    shared = tmp_path / "comfy-temp/h3_prompt_studio"
    shared.mkdir()
    other = shared / "other-extension.txt"
    other.write_text("keep")
    second = load_module("h3_media_second", source)
    assert first.CACHE_ROOT != second.CACHE_ROOT
    assert previous.read_text() == other.read_text() == "keep"
    session = "12345678-1234-4234-8234-123456789abc"
    owned = second.CACHE_ROOT / session
    owned.mkdir()
    (owned / "temporary.txt").write_text("remove")
    second.STORE.clear(session)
    assert not owned.exists()
    assert previous.exists() and other.exists()


def test_published_node_python_parses_and_avoids_private_core_helper():
    for path in (builder.BUNDLE / "custom_nodes").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ImportFrom) and node.module == "comfy.ref2va_contract"
                       for node in ast.walk(tree)), path
