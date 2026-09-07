"""Validate the public H3 assets and create reproducible release archives."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from comfyui_remote_panel import __version__
from comfyui_remote_panel.preset import load_presets

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "h3-workflows"
CANONICAL = ROOT / "src/comfyui_remote_panel/workflows"
IDS = tuple(f"{family}_{mode}_{backend}" for family in ("fl2va", "ref2va")
            for mode in ("original", "lightx2v", "v4step600")
            for backend in ("raw", "ollama", "qwen35"))


def example_prompt(preset):
    values = {name: spec.get("default") for name, spec in preset.manifest["parameters"].items()}
    values.update(prompt="A person walks through a garden.", seed="1")
    media = ({"first": "reference-image.png"} if preset.manifest["family"] == "fl2va"
             else {"image_0": "reference-image.png", "video_0": "reference-video.mp4"})
    graph = preset.build_prompt(values, "12345678-1234-4234-8234-123456789abc", media)
    # The Panel randomizes FL2VA Ollama's writer seed at submission time.
    # Published examples use a small fixed seed, also exact in JavaScript.
    for node in graph.values():
        if node["class_type"] == "H3PromptStandardizer":
            node["inputs"]["seed"] = 1
    return graph


def graph_to_prompt(graph: dict, widgets: dict) -> dict:
    """Read native serialized links and widgets, with no ComfyUI/GPU dependency."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise ValueError("Duplicate visual node IDs")
    links = {link[0]: link for link in graph["links"]}
    if len(links) != len(graph["links"]):
        raise ValueError("Duplicate visual link IDs")
    result = {}
    for node in nodes.values():
        if node.get("mode", 0) != 0:
            raise ValueError("Muted/bypassed nodes are not release examples")
        source_id = node["properties"]["comfy_remote_source_id"]
        if source_id in result:
            raise ValueError("Duplicate source node IDs")
        inputs = {name: value for name, value in zip(widgets[node["type"]], node.get("widgets_values", [])) if name is not None}
        for slot, inp in enumerate(node.get("inputs", [])):
            if inp.get("link") is None:
                continue
            link = links[inp["link"]]
            if link[3:5] != [node["id"], slot]:
                raise ValueError("Mismatched visual input link")
            origin = nodes[link[1]]
            if link[0] not in (origin["outputs"][link[2]].get("links") or []):
                raise ValueError("Missing visual output link")
            inputs[inp["name"]] = [origin["properties"]["comfy_remote_source_id"], link[2]]
        result[source_id] = {"class_type": node["type"], "inputs": inputs}
    return result


def validate() -> None:
    presets = load_presets()
    widgets = json.loads((BUNDLE / "widget-map.json").read_text(encoding="utf-8"))
    files = {path.stem for path in (BUNDLE / "comfyui").glob("*.json")}
    if files != set(IDS):
        raise ValueError("Expected exactly 18 canonical visual workflows")
    for name in IDS:
        expected = example_prompt(presets[name])
        graph = json.loads((BUNDLE / "comfyui" / f"{name}.json").read_text(encoding="utf-8"))
        actual = graph_to_prompt(graph, widgets)
        if set(actual) != set(expected):
            raise ValueError(f"{name}: visual/API node mismatch")
        for node_id, node in expected.items():
            if actual[node_id]["class_type"] != node["class_type"]:
                raise ValueError(f"{name}/{node_id}: node type mismatch")
            for key, value in node["inputs"].items():
                if actual[node_id]["inputs"].get(key) != value:
                    raise ValueError(f"{name}/{node_id}/{key}: visual/API input mismatch")
            for key, value in actual[node_id]["inputs"].items():
                if isinstance(value, list) and key not in node["inputs"]:
                    raise ValueError(f"{name}/{node_id}/{key}: unexpected connection")


def write_archive(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def source_bytes(path: Path) -> bytes:
    # Git's platform-specific checkout line endings must not change ZIP hashes.
    return path.read_text(encoding="utf-8").encode("utf-8")


def build(destination: Path) -> list[Path]:
    validate()
    destination.mkdir(parents=True, exist_ok=True)
    shared = {name: source_bytes(BUNDLE / name) for name in ("README.md", "README.zh-CN.md", "THIRD_PARTY_NOTICES.md", "WORKFLOW_TEMPLATES_LICENSE")}
    shared["LICENSE"] = source_bytes(ROOT / "LICENSE")
    panel = dict(shared)
    for name in IDS:
        family, mode, backend = name.split("_")
        for filename in ("manifest.json", "workflow.json"):
            relative = f"{family}/{mode}/{backend}/{filename}"
            panel[f"workflows/{relative}"] = source_bytes(CANONICAL / relative)
    visual = dict(shared)
    visual.update({f"comfyui/{name}.json": source_bytes(BUNDLE / "comfyui" / f"{name}.json") for name in IDS})
    nodes = dict(shared)
    for name in ("download_resources.py", "resources.json", "node-provenance.json"):
        nodes[name] = source_bytes(BUNDLE / name)
    # Explicit source inventory prevents downloaded guides, caches, or local
    # configuration from being silently added to a release.
    inventory = json.loads((BUNDLE / "node-provenance.json").read_text(encoding="utf-8"))
    for item in inventory:
        content = source_bytes(BUNDLE / "custom_nodes" / item["file"])
        if hashlib.sha256(content).hexdigest() != item["bundled_sha256"]:
            raise ValueError(f"Node provenance checksum mismatch: {item['file']}")
        nodes[f"custom_nodes/{item['file']}"] = content
    outputs = []
    for kind, files in (("panel", panel), ("comfyui", visual), ("nodes", nodes)):
        path = destination / f"comfy-remote-h3-{kind}-{__version__}.zip"
        write_archive(path, files)
        outputs.append(path)
    checksums = destination / f"comfy-remote-h3-{__version__}-SHA256SUMS.txt"
    checksums.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in outputs), encoding="utf-8")
    return [*outputs, checksums]


if __name__ == "__main__":
    for output in build(ROOT / "dist"):
        print(output.name)
