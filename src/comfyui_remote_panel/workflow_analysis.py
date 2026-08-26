from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any, Iterable


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Diagnostic:
    section: str
    severity: Severity
    code: str
    message: str
    node: str | None = None
    input: str | None = None


@dataclass
class ParameterBinding:
    id: str
    semantic: str
    node: str
    input: str
    label: str
    type: str
    control: str
    default: Any = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    values: dict[str, Any] | None = None
    required: bool = False
    confidence: Confidence = Confidence.LOW
    source: str = "heuristic"
    advanced: bool = True


@dataclass
class MediaInput:
    id: str
    semantic: str
    node: str
    input: str
    label: str
    kind: str
    required: bool
    confidence: Confidence
    class_type: str
    default: Any = None


@dataclass
class WorkflowOutput:
    id: str
    node: str
    class_type: str
    kind: str
    confidence: Confidence
    primary: bool = False


@dataclass
class CapabilityProfile:
    output_type: str = "file"
    output_types: list[str] = field(default_factory=list)
    generation_mode: str = "unknown"
    positive_prompt: bool = False
    negative_prompt: bool = False
    media_inputs: dict[str, int] = field(default_factory=dict)
    required_media_inputs: dict[str, int] = field(default_factory=dict)
    size_strategy: str = "unknown"
    batch_strategy: str = "workflow_fixed"
    configurable_parameters: list[str] = field(default_factory=list)


@dataclass
class WorkflowAnalysis:
    nodes: list[dict[str, Any]]
    outputs: list[WorkflowOutput]
    capabilities: CapabilityProfile
    parameters: list[ParameterBinding]
    media_inputs: list[MediaInput]
    diagnostics: list[Diagnostic]
    confidence: Confidence
    preflight: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # asdict preserves Enum subclasses as Enum objects; normalize explicitly so
        # aiohttp/json and persisted manifests never depend on Enum serialization.
        def normalize(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, dict):
                return {key: normalize(child) for key, child in value.items()}
            if isinstance(value, list):
                return [normalize(child) for child in value]
            return value

        result = normalize(data)
        # Compatibility bridge for the v0.2 importer. Configurator 2.0 consumes
        # the first-class fields above, but keeping this view makes old clients
        # degrade gracefully during a rolling upgrade.
        basics = {
            "positive_prompt", "negative_prompt", "prompt", "width", "height", "batch_size",
            "duration", "duration_seconds", "aspect_ratio", "resolution", "megapixels",
        }
        result["basic_bindings"] = {
            "parameters": [item for item in result["parameters"] if item["semantic"] in basics],
            "media": {
                "reference_image": [item for item in result["media_inputs"] if item["kind"] == "image"]
            },
            "outputs": result["outputs"],
            "warnings": [
                item["message"] for item in result["diagnostics"]
                if item["severity"] in {Severity.WARN.value, Severity.FAIL.value}
            ],
        }
        result["output_candidates"] = result["outputs"]
        return result


_CONNECTION = tuple[str, int]
_HELPER_INPUTS = {
    "upload", "control_after_generate", "choose file to upload", "preview", "widget",
}
_SYSTEM_INPUTS = {
    "filename_prefix", "save_output", "output_path", "filename", "subfolder",
}
_BASIC_SEMANTICS = {
    "positive_prompt", "negative_prompt", "prompt", "width", "height", "batch_size",
    "duration", "duration_seconds", "aspect_ratio", "resolution", "megapixels",
}
_LABELS = {
    "positive_prompt": "正面提示词",
    "negative_prompt": "负面提示词",
    "prompt": "提示词",
    "width": "宽度",
    "height": "高度",
    "batch_size": "生成数量",
    "seed": "Seed",
    "steps": "Steps",
    "cfg": "CFG",
    "sampler": "Sampler",
    "scheduler": "Scheduler",
    "denoise": "Denoise",
    "checkpoint": "Checkpoint",
    "lora": "LoRA",
    "vae": "VAE",
    "duration": "Duration",
    "duration_seconds": "时长",
}


def connection(value: Any) -> _CONNECTION | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    node_id, output_index = value
    if not isinstance(node_id, (str, int)) or isinstance(node_id, bool):
        return None
    if not isinstance(output_index, int) or isinstance(output_index, bool):
        return None
    return str(node_id), output_index


def _schema_for(class_type: str, object_info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not object_info or class_type not in object_info:
        return None
    raw = object_info[class_type]
    if not isinstance(raw, dict):
        return None
    if class_type in raw and isinstance(raw[class_type], dict):
        raw = raw[class_type]
    if raw.get("__missing__") is True or raw.get("__error__"):
        return None
    return raw


def _input_schema(schema: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(schema, dict):
        return result
    groups = schema.get("input", {})
    if not isinstance(groups, dict):
        return result
    for group_name in ("required", "optional", "hidden"):
        group = groups.get(group_name, {})
        if not isinstance(group, dict):
            continue
        for name, raw in group.items():
            item = _parse_schema_spec(raw)
            item["required"] = group_name == "required"
            item["hidden"] = group_name == "hidden"
            result[str(name)] = item
    return result


def _parse_schema_spec(raw: Any) -> dict[str, Any]:
    type_raw: Any = None
    options: dict[str, Any] = {}
    if isinstance(raw, (list, tuple)) and raw:
        type_raw = raw[0]
        if len(raw) > 1 and isinstance(raw[1], dict):
            options = raw[1]
    else:
        type_raw = raw

    values: dict[str, Any] | None = None
    if isinstance(type_raw, (list, tuple)):
        kind = "enum"
        values = {str(value): value for value in type_raw}
    else:
        normalized = str(type_raw or "").upper()
        kind = {
            "INT": "integer",
            "FLOAT": "number",
            "STRING": "string",
            "BOOLEAN": "boolean",
            "BOOL": "boolean",
        }.get(normalized, "unsupported")

    control = {
        "enum": "select", "boolean": "switch", "integer": "number",
        "number": "slider" if options.get("slider") else "number",
        "string": "textarea" if options.get("multiline") else "text",
    }.get(kind, "unsupported")
    result = {
        "type": kind,
        "control": control,
        "default": options.get("default"),
        "minimum": options.get("min"),
        "maximum": options.get("max"),
        "step": options.get("step"),
        "values": values,
    }
    return result


def _value_schema(value: Any, input_name: str) -> dict[str, Any]:
    if isinstance(value, bool):
        kind, control = "boolean", "switch"
    elif isinstance(value, int) and not isinstance(value, bool):
        kind, control = "integer", "number"
    elif isinstance(value, float):
        kind, control = "number", "number"
    elif isinstance(value, str):
        kind = "string"
        control = "textarea" if re.search(r"(?:text|prompt|caption)", input_name, re.I) else "text"
    else:
        kind, control = "unsupported", "unsupported"
    return {
        "type": kind, "control": control, "default": value,
        "minimum": None, "maximum": None, "step": None, "values": None,
        "required": False, "hidden": False,
    }


def _semantic(class_type: str, input_name: str) -> tuple[str, Confidence]:
    cls = class_type.lower()
    name = input_name.lower()
    if name == "seed" or name.endswith("_seed"):
        return "seed", Confidence.HIGH if "sampler" in cls else Confidence.MEDIUM
    if name == "steps" or name.endswith("_steps"):
        return "steps", Confidence.HIGH if "sampler" in cls else Confidence.MEDIUM
    if name in {"cfg", "cfg_scale"}:
        return "cfg", Confidence.HIGH if "sampler" in cls else Confidence.MEDIUM
    if name in {"sampler", "sampler_name"}:
        return "sampler", Confidence.HIGH
    if name == "scheduler" or name.endswith("_scheduler"):
        return "scheduler", Confidence.HIGH
    if name in {"denoise", "denoise_strength", "strength"}:
        return "denoise", Confidence.HIGH if "sampler" in cls else Confidence.MEDIUM
    if name in {"ckpt_name", "checkpoint", "checkpoint_name"}:
        return "checkpoint", Confidence.HIGH if "checkpoint" in cls else Confidence.MEDIUM
    if name in {"lora_name", "lora"}:
        return "lora", Confidence.HIGH if "lora" in cls else Confidence.MEDIUM
    if name in {"vae_name", "vae"} and "loader" in cls:
        return "vae", Confidence.HIGH
    if name in {"width", "height", "batch_size"}:
        return name, Confidence.MEDIUM
    if name in {"duration", "duration_seconds", "length", "frames"}:
        return "duration_seconds" if name != "frames" else "duration", Confidence.MEDIUM
    if re.search(r"negative.*prompt|prompt.*negative", name):
        return "negative_prompt", Confidence.MEDIUM
    if re.search(r"positive.*prompt|prompt.*positive", name):
        return "positive_prompt", Confidence.MEDIUM
    if name in {"text", "prompt", "caption"}:
        return "prompt", Confidence.LOW
    return input_name, Confidence.LOW


def _unique_id(semantic: str, node: str, input_name: str, used: set[str]) -> str:
    candidate = re.sub(r"[^a-z0-9._-]+", "_", semantic.lower()).strip("._-") or "parameter"
    if candidate not in used:
        used.add(candidate)
        return candidate
    suffix = re.sub(r"[^a-z0-9._-]+", "_", f"{node}_{input_name}".lower()).strip("._-")
    candidate = f"{candidate}_{suffix}"
    serial = 2
    while candidate in used:
        candidate = f"{candidate}_{serial}"
        serial += 1
    used.add(candidate)
    return candidate


def _literal_text_binding(
    workflow: dict[str, Any], node_id: str, visited: set[str] | None = None
) -> tuple[str, str, Any] | None:
    visited = set() if visited is None else visited
    node_id = str(node_id)
    if node_id in visited:
        return None
    visited.add(node_id)
    node = workflow.get(node_id)
    if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
        return None
    inputs = node["inputs"]
    for name in ("text", "prompt", "positive_prompt", "negative_prompt", "caption"):
        if isinstance(inputs.get(name), str):
            return node_id, name, inputs[name]
    for name, value in inputs.items():
        if isinstance(value, str) and re.search(r"(?:text|prompt|caption)", name, re.I):
            return node_id, str(name), value
    for value in inputs.values():
        source = connection(value)
        if source:
            found = _literal_text_binding(workflow, source[0], visited)
            if found:
                return found
    return None


def _graph(workflow: dict[str, Any]) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str, int]]]]:
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    incoming: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for target_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        for input_name, value in node["inputs"].items():
            source = connection(value)
            if source:
                outgoing[source[0]].append((str(target_id), str(input_name)))
                incoming[str(target_id)].append((source[0], str(input_name), source[1]))
    return outgoing, incoming


def _ancestors(start: str, incoming: dict[str, list[tuple[str, str, int]]]) -> set[str]:
    result: set[str] = set()
    queue = deque([str(start)])
    while queue:
        node = queue.popleft()
        for source, _, _ in incoming.get(node, []):
            if source not in result:
                result.add(source)
                queue.append(source)
    return result


def _descendants(start: str, outgoing: dict[str, list[tuple[str, str]]]) -> set[str]:
    result: set[str] = set()
    queue = deque([str(start)])
    while queue:
        node = queue.popleft()
        for target, _ in outgoing.get(node, []):
            if target not in result:
                result.add(target)
                queue.append(target)
    return result


def _samplers(workflow: dict[str, Any]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        cls = str(node.get("class_type", ""))
        inputs = node["inputs"]
        score = 4 if "sampler" in cls.lower() else 0
        score += 2 if connection(inputs.get("positive")) else 0
        score += 2 if connection(inputs.get("negative")) else 0
        score += 2 if connection(inputs.get("latent_image")) else 0
        if score:
            ranked.append((score, str(node_id)))
    return [node for _, node in sorted(ranked, reverse=True)]


def _output_kind(class_type: str, schema: dict[str, Any] | None) -> tuple[str | None, Confidence]:
    lowered = class_type.lower()
    if re.search(r"(?:save|preview).*image|image.*(?:save|preview)", lowered):
        return "image", Confidence.HIGH
    if "vhs_videocombine" in lowered or re.search(r"(?:save|combine|output).*video|video.*(?:save|combine|output)", lowered):
        return "video", Confidence.HIGH
    if re.search(r"(?:save|output).*audio|audio.*(?:save|output)", lowered):
        return "audio", Confidence.HIGH
    if "save" in lowered or "output" in lowered:
        return "file", Confidence.MEDIUM
    output_types = schema.get("output") if isinstance(schema, dict) else None
    if isinstance(output_types, (list, tuple)):
        names = {str(value).upper() for value in output_types}
        if "VIDEO" in names:
            return "video", Confidence.MEDIUM
        if "IMAGE" in names:
            return "image", Confidence.MEDIUM
        if "AUDIO" in names:
            return "audio", Confidence.MEDIUM
    return None, Confidence.LOW


def _preflight(
    diagnostics: list[Diagnostic], outputs: list[WorkflowOutput], media: list[MediaInput],
    parameters: list[ParameterBinding], capabilities: CapabilityProfile,
) -> dict[str, dict[str, Any]]:
    def section(name: str, default: Severity, message: str) -> dict[str, Any]:
        relevant = [item for item in diagnostics if item.section == name]
        # Known frontend-only helper fields such as LoadImage.upload are useful
        # diagnostic context but do not make the runtime node incompatible.
        gating = [item for item in relevant if item.code != "frontend_helper_input"]
        severity = default
        if any(item.severity == Severity.FAIL for item in gating):
            severity = Severity.FAIL
        elif any(item.severity == Severity.WARN for item in gating) and severity != Severity.FAIL:
            severity = Severity.WARN
        return {
            "status": severity.value,
            "message": message,
            "details": [item.message for item in relevant],
        }

    required = [item for item in media if item.required]
    media_summary = ", ".join(
        f"{sum(item.kind == kind for item in required)} required {kind} input"
        for kind in ("image", "video", "audio") if any(item.kind == kind for item in required)
    ) or "No required remote media inputs"
    parameter_message = "Schema/graph parameter mapping ready"
    if capabilities.size_strategy == "inherit_input":
        parameter_message += "; width/height inherited from source input"
    if capabilities.batch_strategy == "workflow_fixed":
        parameter_message += "; batch controlled by workflow"
    result = {
        "json": section("json", Severity.PASS, "API Workflow JSON parsed"),
        "nodes": section("nodes", Severity.PASS, "Node compatibility checked"),
        "inputs": section("inputs", Severity.PASS, media_summary),
        "parameters": section("parameters", Severity.PASS, parameter_message),
        "outputs": section("outputs", Severity.PASS if outputs else Severity.FAIL, f"{len(outputs)} output(s) detected" if outputs else "No valid output detected"),
        "runtime": {"status": Severity.WARN.value, "message": "Not tested", "details": []},
    }
    if not outputs:
        result["outputs"]["details"].append("工作流没有可识别的有效输出")
    return result


def analyze_workflow(
    workflow: dict[str, Any], object_info: dict[str, Any] | None = None
) -> WorkflowAnalysis:
    if not isinstance(workflow, dict):
        raise ValueError("API Workflow 顶层必须是对象")

    diagnostics: list[Diagnostic] = []
    nodes: list[dict[str, Any]] = []
    normalized_schemas: dict[str, dict[str, Any] | None] = {}
    node_input_schemas: dict[str, dict[str, dict[str, Any]]] = {}

    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise ValueError("API Workflow 节点结构无效")
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(class_type, str) or not isinstance(inputs, dict):
            raise ValueError(f"节点 {node_id} 缺少 class_type 或 inputs")
        schema = _schema_for(class_type, object_info)
        normalized_schemas[str(node_id)] = schema
        input_schema = _input_schema(schema)
        node_input_schemas[str(node_id)] = input_schema
        if object_info is not None and schema is None:
            diagnostics.append(Diagnostic(
                "nodes", Severity.FAIL, "missing_node", f"缺少节点或无法读取节点定义：{class_type}", str(node_id)
            ))
        items: list[dict[str, Any]] = []
        for name, value in inputs.items():
            source = connection(value)
            spec = input_schema.get(str(name))
            if schema is not None and str(name) not in input_schema:
                lowered = str(name).lower()
                if lowered in _HELPER_INPUTS or (class_type.lower() == "loadimage" and lowered == "upload"):
                    diagnostics.append(Diagnostic(
                        "nodes", Severity.WARN, "frontend_helper_input",
                        f"忽略前端辅助字段：{class_type}.{name}", str(node_id), str(name)
                    ))
                elif source:
                    diagnostics.append(Diagnostic(
                        "nodes", Severity.FAIL, "unknown_connected_input",
                        f"节点连接输入未在当前 Schema 中声明：{class_type}.{name}", str(node_id), str(name)
                    ))
                else:
                    diagnostics.append(Diagnostic(
                        "nodes", Severity.WARN, "legacy_or_unknown_input",
                        f"节点存在 Schema 未声明的字段，将按兼容字段保留：{class_type}.{name}", str(node_id), str(name)
                    ))
            items.append({
                "name": str(name),
                "value": None if source else value,
                "connected": source is not None,
                "connection": None if source is None else {"node": source[0], "output": source[1]},
                "schema": None if spec is None else {key: value for key, value in spec.items() if key != "hidden"},
            })
        nodes.append({"id": str(node_id), "class_type": class_type, "inputs": items})

    outgoing, incoming = _graph(workflow)
    samplers = _samplers(workflow)
    used_parameter_ids: set[str] = set()
    bound_targets: set[tuple[str, str]] = set()
    parameters: list[ParameterBinding] = []

    def add_parameter(
        semantic: str, node_id: str, input_name: str, confidence: Confidence,
        source: str, *, label: str | None = None, force_advanced: bool | None = None,
    ) -> None:
        target = (str(node_id), str(input_name))
        if target in bound_targets:
            return
        node = workflow[str(node_id)]
        value = node["inputs"][input_name]
        schema_spec = node_input_schemas[str(node_id)].get(str(input_name))
        spec = dict(schema_spec) if schema_spec is not None else _value_schema(value, str(input_name))
        if spec.get("hidden") or spec.get("type") == "unsupported":
            return
        parameter_id = _unique_id(semantic, str(node_id), str(input_name), used_parameter_ids)
        advanced = semantic not in _BASIC_SEMANTICS if force_advanced is None else force_advanced
        parameters.append(ParameterBinding(
            id=parameter_id, semantic=semantic, node=str(node_id), input=str(input_name),
            label=label or _LABELS.get(semantic, str(input_name).replace("_", " ").title()),
            type=spec["type"], control=spec["control"], default=value,
            minimum=spec.get("minimum"), maximum=spec.get("maximum"), step=spec.get("step"),
            values=spec.get("values"), required=bool(spec.get("required")),
            confidence=confidence, source=source, advanced=advanced,
        ))
        bound_targets.add(target)

    # Graph semantics take priority over names: trace KSampler positive/negative
    # edges back to literal text encoders.
    for sampler_id in samplers:
        sampler_inputs = workflow[sampler_id]["inputs"]
        for edge_name, semantic in (("positive", "positive_prompt"), ("negative", "negative_prompt")):
            source = connection(sampler_inputs.get(edge_name))
            if not source:
                continue
            binding = _literal_text_binding(workflow, source[0])
            if binding:
                node_id, input_name, _ = binding
                add_parameter(semantic, node_id, input_name, Confidence.HIGH, "graph", force_advanced=False)

    # Determine latent source topology before classifying media and size.
    latent_ancestors: set[str] = set()
    empty_latent_nodes: set[str] = set()
    vae_encode_nodes: set[str] = set()
    for sampler_id in samplers:
        source = connection(workflow[sampler_id]["inputs"].get("latent_image"))
        if source:
            latent_ancestors.add(source[0])
            latent_ancestors.update(_ancestors(source[0], incoming))
    for node_id in latent_ancestors:
        cls = str(workflow.get(node_id, {}).get("class_type", "")).lower()
        if "emptylatent" in cls or ("latent" in cls and "empty" in cls):
            empty_latent_nodes.add(node_id)
        if "vaeencode" in cls or ("vae" in cls and "encode" in cls):
            vae_encode_nodes.add(node_id)

    media_inputs: list[MediaInput] = []
    for node_id, node in workflow.items():
        class_type = str(node["class_type"])
        lowered = class_type.lower()
        if not ("load" in lowered and any(kind in lowered for kind in ("image", "video", "audio"))):
            continue
        kind = "image" if "image" in lowered else ("video" if "video" in lowered else "audio")
        candidates = ("image", "file", "video", "audio", "path")
        input_name = next((name for name in candidates if name in node["inputs"] and connection(node["inputs"][name]) is None), None)
        if not input_name:
            continue
        descendants = _descendants(str(node_id), outgoing)
        active = bool(descendants) or not outgoing.get(str(node_id))
        if not active:
            continue
        source_image = kind == "image" and any(vae_id in descendants for vae_id in vae_encode_nodes)
        semantic = "source_image" if source_image else f"reference_{kind}"
        confidence = Confidence.HIGH if source_image else Confidence.MEDIUM
        required = source_image or bool(node_input_schemas[str(node_id)].get(input_name, {}).get("required"))
        media_inputs.append(MediaInput(
            id=f"{kind}_{len([item for item in media_inputs if item.kind == kind])}",
            semantic=semantic, node=str(node_id), input=input_name,
            label="源图" if source_image else {"image": "参考图", "video": "参考视频", "audio": "参考音频"}[kind],
            kind=kind, required=required, confidence=confidence,
            class_type=class_type, default=node["inputs"].get(input_name),
        ))

    # Empty latent dimensions are graph-confirmed generation controls.
    for node_id in sorted(empty_latent_nodes):
        for input_name in ("width", "height", "batch_size"):
            if input_name in workflow[node_id]["inputs"] and connection(workflow[node_id]["inputs"][input_name]) is None:
                add_parameter(input_name, node_id, input_name, Confidence.HIGH, "graph", force_advanced=False)

    # Schema-driven editable literals. Advanced runtime choices are intentionally
    # retained; names such as ckpt_name/sampler_name/scheduler/lora_name are no
    # longer excluded merely because they look model-internal.
    for node_id, node in workflow.items():
        for input_name, value in node["inputs"].items():
            if connection(value) is not None or (str(node_id), str(input_name)) in bound_targets:
                continue
            lowered = str(input_name).lower()
            if lowered in _HELPER_INPUTS or lowered in _SYSTEM_INPUTS:
                continue
            # Loader media inputs are represented as media slots, never as text/enums.
            if any(item.node == str(node_id) and item.input == str(input_name) for item in media_inputs):
                continue
            schema_spec = node_input_schemas[str(node_id)].get(str(input_name))
            semantic, semantic_confidence = _semantic(str(node["class_type"]), str(input_name))
            if schema_spec is not None and not schema_spec.get("hidden") and schema_spec.get("type") != "unsupported":
                confidence = semantic_confidence if semantic_confidence != Confidence.LOW else Confidence.MEDIUM
                add_parameter(semantic, str(node_id), str(input_name), confidence, "schema")
            else:
                # Heuristic is fallback only. Keep recognizable scalar controls as
                # LOW-confidence manual candidates instead of silently guessing.
                inferred = _value_schema(value, str(input_name))
                if inferred["type"] != "unsupported" and semantic_confidence != Confidence.LOW:
                    add_parameter(semantic, str(node_id), str(input_name), Confidence.LOW, "heuristic")

    # Prompt fallback is deliberately weak and only used when graph semantics were
    # unavailable. It must not silently invent positive/negative roles.
    if not any(item.semantic in {"positive_prompt", "prompt"} for item in parameters):
        text_candidates: list[tuple[str, str]] = []
        for node_id, node in workflow.items():
            for input_name, value in node["inputs"].items():
                if isinstance(value, str) and re.search(r"(?:text|prompt|caption)", str(input_name), re.I):
                    text_candidates.append((str(node_id), str(input_name)))
        if text_candidates:
            node_id, input_name = text_candidates[0]
            add_parameter("prompt", node_id, input_name, Confidence.LOW, "heuristic", force_advanced=False)
            diagnostics.append(Diagnostic(
                "parameters", Severity.WARN, "low_confidence_prompt",
                "提示词仅通过字段名推测，需要用户确认映射", node_id, input_name,
            ))

    # Output detection combines known output nodes, schema output types and graph
    # terminal position. A schema type alone is only considered on terminal nodes.
    outputs: list[WorkflowOutput] = []
    for node_id, node in workflow.items():
        class_type = str(node["class_type"])
        kind, confidence = _output_kind(class_type, normalized_schemas[str(node_id)])
        terminal = not outgoing.get(str(node_id))
        known_output = confidence == Confidence.HIGH or bool(re.search(r"(?:save|preview|output|combine)", class_type, re.I))
        if kind and (known_output or terminal):
            outputs.append(WorkflowOutput(
                id=f"output_{len(outputs)}", node=str(node_id), class_type=class_type,
                kind=kind, confidence=confidence,
            ))
    if outputs:
        outputs[0].primary = True
    else:
        diagnostics.append(Diagnostic("outputs", Severity.FAIL, "missing_output", "未能识别有效输出节点"))

    image_source_required = any(item.semantic == "source_image" and item.required for item in media_inputs)
    if image_source_required and vae_encode_nodes:
        generation_mode = "img2img"
        size_strategy = "inherit_input"
    elif empty_latent_nodes:
        generation_mode = "txt2img"
        size_strategy = "configurable" if {"width", "height"} <= {item.semantic for item in parameters} else "workflow_fixed"
    elif any(item.kind == "video" for item in media_inputs) or any(item.kind == "video" for item in outputs):
        generation_mode = "video"
        size_strategy = "workflow_fixed"
    else:
        generation_mode = "generic"
        size_strategy = "workflow_fixed"

    if any(item.semantic == "width" for item in parameters) and any(item.semantic == "height" for item in parameters):
        if generation_mode != "img2img":
            size_strategy = "configurable"
    batch_strategy = "configurable" if any(item.semantic == "batch_size" for item in parameters) else "workflow_fixed"
    output_types = list(dict.fromkeys(item.kind for item in outputs))
    capabilities = CapabilityProfile(
        output_type=outputs[0].kind if outputs else "file",
        output_types=output_types,
        generation_mode=generation_mode,
        positive_prompt=any(item.semantic in {"positive_prompt", "prompt"} for item in parameters),
        negative_prompt=any(item.semantic == "negative_prompt" for item in parameters),
        media_inputs={kind: sum(item.kind == kind for item in media_inputs) for kind in ("image", "video", "audio") if any(item.kind == kind for item in media_inputs)},
        required_media_inputs={kind: sum(item.kind == kind and item.required for item in media_inputs) for kind in ("image", "video", "audio") if any(item.kind == kind and item.required for item in media_inputs)},
        size_strategy=size_strategy,
        batch_strategy=batch_strategy,
        configurable_parameters=[item.id for item in parameters],
    )

    if not capabilities.positive_prompt:
        diagnostics.append(Diagnostic("inputs", Severity.WARN, "prompt_not_detected", "未能可靠识别正面提示词；该工作流也可能本来就不需要提示词"))
    low_parameters = [item for item in parameters if item.confidence == Confidence.LOW]
    if low_parameters:
        diagnostics.append(Diagnostic(
            "parameters", Severity.WARN, "manual_mapping_required",
            f"{len(low_parameters)} 个参数仅为低置信度候选，应在高级手动映射中确认",
        ))

    critical_confidences: list[Confidence] = [item.confidence for item in outputs]
    critical_confidences.extend(item.confidence for item in media_inputs if item.required)
    critical_confidences.extend(
        item.confidence for item in parameters if item.semantic in {"positive_prompt", "negative_prompt", "width", "height"}
    )
    if any(item == Confidence.LOW for item in critical_confidences):
        overall_confidence = Confidence.LOW
    elif critical_confidences and all(item == Confidence.HIGH for item in critical_confidences):
        overall_confidence = Confidence.HIGH
    else:
        overall_confidence = Confidence.MEDIUM

    preflight = _preflight(diagnostics, outputs, media_inputs, parameters, capabilities)
    return WorkflowAnalysis(
        nodes=nodes, outputs=outputs, capabilities=capabilities, parameters=parameters,
        media_inputs=media_inputs, diagnostics=diagnostics, confidence=overall_confidence,
        preflight=preflight,
    )


def advertised_inputs(object_info: dict[str, Any] | None, class_type: str) -> set[str]:
    """Return current runtime inputs for one node type.

    Kept public so ComfyClient can share exactly the same schema interpretation as
    Configurator 2.0 instead of maintaining a second compatibility algorithm.
    """
    return set(_input_schema(_schema_for(class_type, object_info)))


def classify_unknown_input(class_type: str, input_name: str, connected: bool = False) -> Severity:
    lowered = input_name.lower()
    if lowered in _HELPER_INPUTS or (class_type.lower() == "loadimage" and lowered == "upload"):
        return Severity.WARN
    return Severity.FAIL if connected else Severity.WARN
