from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from .preset import PresetError, preset_from_definition
from .workflow_analysis import WorkflowAnalysis, analyze_workflow


MAX_WORKFLOW_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 8 * 1024 * 1024
WORKFLOW_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
WINDOWS_PATH = re.compile(r"(?i)^[a-z]:[\\/]")
SECRET_KEYS = {"password", "secret", "token", "api_key", "apikey", "authorization"}


def parse_json_bytes(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_WORKFLOW_BYTES:
        raise PresetError("工作流 JSON 不能超过 4MB")
    try:
        text = payload.decode("utf-8-sig").strip()
        fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PresetError("工作流 JSON 无效；请使用 ComfyUI 的“导出（API）”文件") from exc
    if not isinstance(value, dict):
        raise PresetError("工作流 JSON 顶层必须是对象")
    return value


def _connection(value: Any) -> tuple[str, int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    node_id, output_index = value
    if not isinstance(node_id, (str, int)) or isinstance(node_id, bool):
        return None
    if not isinstance(output_index, int) or isinstance(output_index, bool):
        return None
    return str(node_id), output_index


def inspect_api_workflow(
    workflow: dict[str, Any], object_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return Configurator 2.0's single authoritative workflow analysis.

    The optional object_info map is keyed by class_type. Values may be either a
    raw node schema or ComfyUI's `{class_type: schema}` endpoint response.
    """
    try:
        return analyze_workflow(workflow, object_info).to_dict()
    except ValueError as exc:
        raise PresetError(str(exc)) from exc


def suggest_control(name: str, value: Any) -> str:
    """Legacy fallback used by older exported clients/manual mapping UIs."""
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


def _analysis_dict(analysis: WorkflowAnalysis | dict[str, Any] | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    if isinstance(analysis, WorkflowAnalysis):
        return analysis.to_dict()
    return analysis if isinstance(analysis, dict) else None


def _parameter_spec(item: dict[str, Any], workflow: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    binding_id = item.get("id") or item.get("semantic")
    node_id, input_name = str(item.get("node")), item.get("input")
    node = workflow.get(node_id)
    if not isinstance(binding_id, str) or not WORKFLOW_ID.fullmatch(binding_id):
        raise PresetError("参数 ID 无效")
    if not isinstance(node, dict) or not isinstance(input_name, str) or input_name not in node.get("inputs", {}):
        raise PresetError(f"参数映射无效：{binding_id}")
    if _connection(node["inputs"][input_name]) is not None:
        raise PresetError(f"不能直接暴露节点连接：{binding_id}")
    kind = item.get("type")
    if kind not in {"string", "integer", "number", "boolean", "enum"}:
        raise PresetError(f"参数类型无效：{binding_id}")
    spec = {
        key: item[key]
        for key in ("type", "default", "minimum", "maximum", "step", "values")
        if key in item and item[key] is not None
    }
    spec.update({"node": node_id, "input": input_name})
    ui = dict(item.get("ui") or {})
    for source_key, target_key in (
        ("label", "label"), ("semantic", "semantic"), ("control", "control"),
        ("confidence", "confidence"), ("source", "source"), ("advanced", "advanced"),
    ):
        if source_key in item and item[source_key] is not None:
            ui[target_key] = item[source_key]
    if ui:
        spec["ui"] = ui
    return binding_id, spec


def build_definition(
    workflow: dict[str, Any], remote_config: dict[str, Any],
    analysis: WorkflowAnalysis | dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(workflow, dict) or not isinstance(remote_config, dict):
        raise PresetError("工作流配置无效")
    analysis_data = _analysis_dict(analysis)
    if analysis_data is None:
        analysis_data = inspect_api_workflow(workflow)

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
        binding_id, spec = _parameter_spec(item, workflow)
        if binding_id in parameters:
            raise PresetError(f"参数 ID 重复：{binding_id}")
        parameters[binding_id] = spec

    outputs = remote_config.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise PresetError("至少选择一个输出节点")
    normalized_outputs: list[dict[str, Any]] = []
    for index, output in enumerate(outputs):
        if not isinstance(output, dict) or str(output.get("node")) not in workflow:
            raise PresetError("输出绑定无效")
        kind = output.get("kind")
        if kind not in {"image", "video", "audio", "file"}:
            raise PresetError("输出类型无效")
        normalized_outputs.append({
            "id": str(output.get("id") or f"output_{index}"),
            "node": str(output["node"]),
            "kind": kind,
            "history_keys": list(output.get("history_keys") or (
                ["images"] if kind == "image" else
                ["videos", "video", "files", "images"] if kind == "video" else
                ["audio", "files"] if kind == "audio" else ["files"]
            )),
            "primary": bool(output.get("primary", index == 0)),
        })
    if not any(item["primary"] for item in normalized_outputs):
        normalized_outputs[0]["primary"] = True

    media = remote_config.get("media", {"type": "none"})
    if not isinstance(media, dict):
        raise PresetError("媒体输入配置无效")

    manifest = {
        "schema_version": 2,
        "revision": int(remote_config.get("revision", 1)),
        "id": workflow_id,
        "name": name.strip(),
        "description": str(remote_config.get("description", "")),
        "family": "generic",
        "minimum_comfyui_version": str(remote_config.get("minimum_comfyui_version", "0.26.0")),
        "workflow": "workflow-api.json",
        "parameters": parameters,
        "input_bindings": {"values": parameters, "media": media},
        "output_bindings": normalized_outputs,
        "output_node": str(next((item for item in normalized_outputs if item["primary"]), normalized_outputs[0])["node"]),
        "locked": [],
        "dependencies": remote_config.get("dependencies", []),
        "stages": remote_config.get("stages", {}),
        "progress_phase": remote_config.get("progress_phase", {}),
        "workflow_analysis_version": 2,
        "capability_profile": analysis_data.get("capabilities", {}),
        "workflow_confidence": analysis_data.get("confidence", "LOW"),
        "preflight": analysis_data.get("preflight", {}),
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
    remote = {key: value for key, value in manifest.items() if key != "workflow"}
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
