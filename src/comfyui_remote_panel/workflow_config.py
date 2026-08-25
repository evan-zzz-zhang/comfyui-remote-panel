from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from .preset import PresetError, preset_from_definition


MAX_WORKFLOW_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 8 * 1024 * 1024
WORKFLOW_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
WINDOWS_PATH = re.compile(r"(?i)^[a-z]:[\\/]")
SECRET_KEYS = {"password", "secret", "token", "api_key", "apikey", "authorization"}


def parse_json_bytes(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_WORKFLOW_BYTES:
        raise PresetError("工作流 JSON 不能超过 4MB")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PresetError("工作流 JSON 无效") from exc
    if not isinstance(value, dict):
        raise PresetError("工作流 JSON 顶层必须是对象")
    return value


def inspect_api_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(workflow, dict):
        raise PresetError("API Workflow 顶层必须是对象")
    nodes: list[dict[str, Any]] = []
    output_candidates: list[dict[str, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise PresetError("API Workflow 节点结构无效")
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(class_type, str) or not isinstance(inputs, dict):
            raise PresetError(f"节点 {node_id} 缺少 class_type 或 inputs")
        items = []
        for name, value in inputs.items():
            connected = isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)
            items.append({
                "name": name, "value": None if connected else value, "connected": connected,
                "suggested_control": suggest_control(name, value) if not connected else None,
            })
        nodes.append({"id": node_id, "class_type": class_type, "inputs": items})
        lowered = class_type.lower()
        if "save" in lowered or "output" in lowered:
            kind = "image" if "image" in lowered else ("video" if "video" in lowered else "file")
            output_candidates.append({"node": node_id, "class_type": class_type, "kind": kind})
    return {"nodes": nodes, "output_candidates": output_candidates}


def suggest_control(name: str, value: Any) -> str:
    lowered = name.lower()
    if "seed" in lowered:
        return "seed"
    if isinstance(value, bool):
        return "switch"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "slider"
    if isinstance(value, str):
        return "textarea" if "text" in lowered or "prompt" in lowered else "text"
    return "unsupported"


def build_definition(workflow: dict[str, Any], remote_config: dict[str, Any]) -> dict[str, Any]:
    inspect_api_workflow(workflow)
    workflow_id = remote_config.get("id")
    name = remote_config.get("name")
    if not isinstance(workflow_id, str) or not WORKFLOW_ID.fullmatch(workflow_id):
        raise PresetError("工作流 ID 只能使用 2–64 位小写字母、数字、点、下划线或连字符")
    if not isinstance(name, str) or not name.strip():
        raise PresetError("工作流名称不能为空")
    parameters: dict[str, Any] = {}
    for item in remote_config.get("parameters", []):
        if not isinstance(item, dict):
            raise PresetError("参数绑定无效")
        binding_id, node_id, input_name = item.get("id"), str(item.get("node")), item.get("input")
        node = workflow.get(node_id)
        if not isinstance(binding_id, str) or not WORKFLOW_ID.fullmatch(binding_id):
            raise PresetError("参数 ID 无效")
        if not isinstance(node, dict) or input_name not in node.get("inputs", {}):
            raise PresetError(f"参数映射无效：{binding_id}")
        if isinstance(node["inputs"][input_name], list):
            raise PresetError(f"不能直接暴露节点连接：{binding_id}")
        spec = {key: item[key] for key in ("type", "default", "minimum", "maximum", "step", "values", "ui") if key in item}
        spec.update({"node": node_id, "input": input_name})
        parameters[binding_id] = spec
    outputs = remote_config.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise PresetError("至少选择一个输出节点")
    for output in outputs:
        if not isinstance(output, dict) or str(output.get("node")) not in workflow:
            raise PresetError("输出绑定无效")
    media = remote_config.get("media", {"type": "none"})
    manifest = {
        "schema_version": 2, "revision": 1, "id": workflow_id,
        "name": name.strip(), "description": str(remote_config.get("description", "")),
        "minimum_comfyui_version": str(remote_config.get("minimum_comfyui_version", "0.26.0")),
        "workflow": "workflow-api.json", "parameters": parameters,
        "input_bindings": {"values": parameters, "media": media},
        "output_bindings": outputs, "output_node": str(outputs[0]["node"]),
        "locked": [], "dependencies": remote_config.get("dependencies", []),
        "stages": remote_config.get("stages", {}), "progress_phase": remote_config.get("progress_phase", {}),
    }
    definition = {"manifest": manifest, "workflow": workflow}
    assert_safe_package(definition)
    preset_from_definition(definition)
    return definition


def assert_safe_package(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRET_KEYS:
                raise PresetError(f"工作流包不得包含密钥字段：{path}.{key}")
            assert_safe_package(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_safe_package(child, f"{path}[{index}]")
    elif isinstance(value, str) and (WINDOWS_PATH.match(value) or value.startswith(("/home/", "/root/", "/Users/"))):
        raise PresetError(f"工作流包不得包含本地绝对路径：{path}")


def export_package(definition: dict[str, Any]) -> bytes:
    assert_safe_package(definition)
    manifest = definition["manifest"]
    metadata = {key: manifest.get(key) for key in ("id", "name", "description", "revision")}
    remote = {key: value for key, value in manifest.items() if key not in {"workflow"}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("workflow-api.json", json.dumps(definition["workflow"], ensure_ascii=False, indent=2))
        archive.writestr("remote-config.json", json.dumps(remote, ensure_ascii=False, indent=2))
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    return buffer.getvalue()


def import_package(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_PACKAGE_BYTES:
        raise PresetError("工作流包不能超过 8MB")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            allowed = {"workflow-api.json", "remote-config.json", "metadata.json", "cover.png", "cover.jpg", "cover.webp"}
            if not names <= allowed or not {"workflow-api.json", "remote-config.json", "metadata.json"} <= names:
                raise PresetError("工作流包文件结构无效")
            workflow = parse_json_bytes(archive.read("workflow-api.json"))
            manifest = parse_json_bytes(archive.read("remote-config.json"))
            manifest.setdefault("workflow", "workflow-api.json")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise PresetError("工作流包无效") from exc
    definition = {"manifest": manifest, "workflow": workflow}
    assert_safe_package(definition)
    preset_from_definition(definition)
    return definition
