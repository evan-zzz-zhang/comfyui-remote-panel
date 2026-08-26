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


def _literal_text_binding(workflow: dict[str, Any], node_id: str, visited: set[str] | None = None) -> dict[str, Any] | None:
    visited = set() if visited is None else visited
    node_id = str(node_id)
    if node_id in visited:
        return None
    visited.add(node_id)
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return None
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return None

    preferred = ("text", "prompt", "positive_prompt", "negative_prompt", "caption")
    for input_name in preferred:
        value = inputs.get(input_name)
        if isinstance(value, str):
            return {"node": node_id, "input": input_name, "default": value}
    for input_name, value in inputs.items():
        if isinstance(value, str) and re.search(r"(?:text|prompt|caption)", input_name, re.IGNORECASE):
            return {"node": node_id, "input": input_name, "default": value}

    for value in inputs.values():
        source = _connection(value)
        if source:
            binding = _literal_text_binding(workflow, source[0], visited)
            if binding:
                return binding
    return None


def _numeric_literal(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _suggest_basic_bindings(
    workflow: dict[str, Any], output_candidates: list[dict[str, str]]
) -> dict[str, Any]:
    parameters: list[dict[str, Any]] = []
    seen_parameter_targets: set[tuple[str, str]] = set()

    def add_parameter(semantic: str, binding: dict[str, Any], label: str, kind: str, control: str) -> None:
        target = (str(binding["node"]), str(binding["input"]))
        if target in seen_parameter_targets:
            return
        seen_parameter_targets.add(target)
        parameters.append({
            "semantic": semantic,
            "node": target[0],
            "input": target[1],
            "label": label,
            "type": kind,
            "control": control,
            "default": binding.get("default"),
        })

    # Prefer the sampler's explicit positive/negative graph edges. This is much
    # less ambiguous than simply listing every CLIP text node in the workflow.
    sampler_nodes: list[tuple[int, str, dict[str, Any]]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        inputs = node["inputs"]
        class_name = str(node.get("class_type", ""))
        score = 0
        if _connection(inputs.get("positive")):
            score += 4
        if _connection(inputs.get("negative")):
            score += 4
        if "sampler" in class_name.lower():
            score += 2
        if score:
            sampler_nodes.append((score, str(node_id), node))
    sampler_nodes.sort(reverse=True, key=lambda item: item[0])

    positive: dict[str, Any] | None = None
    negative: dict[str, Any] | None = None
    for _, _, node in sampler_nodes:
        inputs = node["inputs"]
        if positive is None:
            source = _connection(inputs.get("positive"))
            if source:
                positive = _literal_text_binding(workflow, source[0])
        if negative is None:
            source = _connection(inputs.get("negative"))
            if source:
                negative = _literal_text_binding(workflow, source[0])
        if positive and negative:
            break

    # Fallback for simple workflows that omit a conventional sampler node.
    text_candidates: list[dict[str, Any]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        for input_name, value in node["inputs"].items():
            if not isinstance(value, str):
                continue
            if not re.search(r"(?:text|prompt|caption)", input_name, re.IGNORECASE):
                continue
            if re.search(r"(?:file|path|model|ckpt|lora|vae)", input_name, re.IGNORECASE):
                continue
            text_candidates.append({"node": str(node_id), "input": input_name, "default": value})
    if positive is None and text_candidates:
        positive = text_candidates[0]
    if negative is None and len(text_candidates) > 1:
        for candidate in text_candidates:
            if not positive or (candidate["node"], candidate["input"]) != (positive["node"], positive["input"]):
                negative = candidate
                break

    if positive:
        add_parameter("positive_prompt", positive, "正面提示词", "string", "textarea")
    if negative:
        add_parameter("negative_prompt", negative, "负面提示词", "string", "textarea")

    # Prefer one image/latent size node and expose width/height/batch as a unit.
    size_candidates: list[tuple[int, str, dict[str, Any]]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        inputs = node["inputs"]
        if not (_numeric_literal(inputs.get("width")) and _numeric_literal(inputs.get("height"))):
            continue
        class_name = str(node.get("class_type", "")).lower()
        score = 1
        if re.search(r"(?:latent|image|size|empty)", class_name):
            score += 3
        if _numeric_literal(inputs.get("batch_size")):
            score += 2
        size_candidates.append((score, str(node_id), node))
    size_candidates.sort(reverse=True, key=lambda item: item[0])
    if size_candidates:
        _, node_id, node = size_candidates[0]
        inputs = node["inputs"]
        add_parameter("width", {"node": node_id, "input": "width", "default": inputs["width"]}, "宽度", "integer", "number")
        add_parameter("height", {"node": node_id, "input": "height", "default": inputs["height"]}, "高度", "integer", "number")
        if _numeric_literal(inputs.get("batch_size")):
            add_parameter(
                "batch_size",
                {"node": node_id, "input": "batch_size", "default": inputs["batch_size"]},
                "批次数量",
                "integer",
                "number",
            )

    if not any(item["semantic"] == "batch_size" for item in parameters):
        for node_id, node in workflow.items():
            if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
                continue
            value = node["inputs"].get("batch_size")
            if _numeric_literal(value):
                add_parameter(
                    "batch_size",
                    {"node": str(node_id), "input": "batch_size", "default": value},
                    "批次数量",
                    "integer",
                    "number",
                )
                break

    image_candidates: list[dict[str, Any]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        class_name = str(node.get("class_type", ""))
        lowered = class_name.lower()
        if not ("load" in lowered and "image" in lowered):
            continue
        for input_name in ("image", "file"):
            if input_name in node["inputs"] and _connection(node["inputs"][input_name]) is None:
                image_candidates.append({
                    "semantic": "reference_image",
                    "node": str(node_id),
                    "input": input_name,
                    "label": "参考图",
                    "kind": "image",
                    "class_type": class_name,
                    "default": node["inputs"][input_name],
                })
                break

    warnings: list[str] = []
    if not positive:
        warnings.append("未能自动识别正面提示词")
    if not output_candidates:
        warnings.append("未能自动识别输出节点")
    if len(image_candidates) > 1:
        warnings.append("检测到多个图片输入，需要确认参考图槽位")
    if len(output_candidates) > 1:
        warnings.append("检测到多个输出节点，需要确认主要输出")

    return {
        "parameters": parameters,
        "media": {"reference_image": image_candidates},
        "outputs": output_candidates,
        "warnings": warnings,
    }


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
            connection = _connection(value)
            items.append({
                "name": name,
                "value": None if connection else value,
                "connected": connection is not None,
                "connection": None if connection is None else {"node": connection[0], "output": connection[1]},
                "suggested_control": suggest_control(name, value) if connection is None else None,
            })
        nodes.append({"id": node_id, "class_type": class_type, "inputs": items})
        lowered = class_type.lower()
        if "save" in lowered or "output" in lowered:
            kind = "image" if "image" in lowered else ("video" if "video" in lowered else "file")
            output_candidates.append({"node": node_id, "class_type": class_type, "kind": kind})
    return {
        "nodes": nodes,
        "output_candidates": output_candidates,
        "basic_bindings": _suggest_basic_bindings(workflow, output_candidates),
    }


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
