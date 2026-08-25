from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .files import FileStore


class PresetError(ValueError):
    pass


@dataclass
class Preset:
    MEGAPIXEL_VALUES = (0.2, 0.4, 0.6, 0.8, 0.9, 1.0)
    directory: Path
    manifest: dict[str, Any]
    template: dict[str, Any]
    available: bool = False
    diagnostics: list[str] = field(default_factory=list)
    model_overrides: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def minimum_version(self) -> str:
        return self.manifest["minimum_comfyui_version"]

    @property
    def output_node(self) -> str:
        return self.manifest["output_node"]

    @property
    def stages(self) -> dict[str, str]:
        return self.manifest.get("stages", {})

    def phase_for_stage(self, stage: str | None) -> str | None:
        if not stage:
            return None
        phases = self.manifest.get("progress_phase", {})
        for node_id, label in self.stages.items():
            if label == stage:
                return phases.get(node_id)
        return {"采样": "sampling", "解码画面": "decode", "解码音频": "decode", "合成视频": "compose", "保存视频": "save"}.get(stage)

    def public_metadata(self) -> dict[str, Any]:
        parameters = self.manifest["parameters"]
        exposed = {}
        for name in ("duration_seconds", "aspect_ratio", "megapixels", "scheduler", "sampler", "steps"):
            spec = parameters[name]
            exposed[name] = {
                key: copy.deepcopy(spec[key])
                for key in ("type", "minimum", "maximum", "step", "default", "values")
                if key in spec
            }
        media = self.manifest.get("reference_media")
        public_media = None if not media else {
            kind: {"max": media[kind]["max"]} for kind in ("images", "videos", "audios")
        }
        return {
            "id": self.id,
            "name": self.manifest["name"],
            "family": self.manifest.get("family", "fl2va"),
            "description": self.manifest.get("description", ""),
            "available": self.available,
            "diagnostics": self.diagnostics,
            "parameters": exposed,
            "reference_media": public_media,
        }

    def validate_parameters(self, values: dict[str, Any], *, allow_empty_prompt: bool = False) -> dict[str, Any]:
        specs = self.manifest["parameters"]
        result: dict[str, Any] = {}
        for name, spec in specs.items():
            value = values.get(name, spec.get("default"))
            if name == "prompt":
                if not isinstance(value, str) or not value.strip():
                    if not allow_empty_prompt:
                        raise PresetError("提示词不能为空")
                    result[name] = ""
                    continue
                result[name] = value.strip()
                continue
            if name == "seed":
                if value is None:
                    result[name] = None
                    continue
                if isinstance(value, int) and not isinstance(value, bool):
                    seed = value
                elif isinstance(value, str) and value.isascii() and value.isdigit():
                    seed = int(value)
                else:
                    raise PresetError("种子必须是整数")
                if seed < spec["minimum"]:
                    raise PresetError(f"{name} 低于允许范围")
                if seed > spec["maximum"]:
                    raise PresetError(f"{name} 超出允许范围")
                result[name] = str(seed)
                continue
            elif spec["type"] == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise PresetError(f"{name} 必须是整数")
            elif spec["type"] == "number":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise PresetError(f"{name} 必须是数字")
                value = round(float(value), 1)
                step = spec.get("step")
                if step and abs((value - spec["minimum"]) / step - round((value - spec["minimum"]) / step)) > 1e-8:
                    raise PresetError(f"{name} 步进不合法")
                if name == "megapixels" and value not in self.MEGAPIXEL_VALUES:
                    raise PresetError("megapixels 不是可用的分辨率预设")
            elif spec["type"] == "enum":
                if value not in spec["values"]:
                    raise PresetError(f"不支持的 {name}")
            if "minimum" in spec and value < spec["minimum"]:
                raise PresetError(f"{name} 低于允许范围")
            if "maximum" in spec and value > spec["maximum"]:
                raise PresetError(f"{name} 超出允许范围")
            result[name] = value
        return result

    def build_prompt(self, values: dict[str, Any], job_id: str, media: dict[str, str]) -> dict[str, Any]:
        allow_empty_prompt = self.manifest.get("family") == "fl2va" and bool({"first", "last"} & media.keys())
        normalized = self.validate_parameters(values, allow_empty_prompt=allow_empty_prompt)
        reference = self.manifest.get("reference_aspect", {})
        aspect_value = normalized.get("aspect_ratio")
        reference_values = {reference.get("parameter_value"), reference.get("legacy_parameter_value", "reference"), reference.get("video_parameter_value")}
        use_reference = aspect_value in reference_values
        prompt = copy.deepcopy(self.template)
        for node_id, inputs in self.model_overrides.items():
            prompt[node_id]["inputs"].update(inputs)
        for name, spec in self.manifest["parameters"].items():
            value = normalized[name]
            if name == "seed":
                value = int(value)
            if spec["type"] == "enum":
                value = spec["values"][value]
                if isinstance(value, str) and value.startswith("__reference_"):
                    continue
            prompt[spec["node"]]["inputs"][spec["input"]] = value
        output_key = FileStore.storage_key(job_id) if len(str(job_id)) >= 36 else str(job_id)
        prompt[self.output_node]["inputs"]["filename_prefix"] = f"h3_remote/{output_key}"
        reference_source: str | None = None
        target = self.manifest["frame_inputs"]["target_node"]
        if self.manifest.get("family") == "ref2va":
            reference_sources = self._add_reference_media(prompt, media)
            source_kind = "video" if aspect_value == reference.get("video_parameter_value") else "image"
            reference_source = reference_sources.get(source_kind)
            if use_reference and reference_source is None:
                label = "参考视频 1" if source_kind == "video" else "参考图 1"
                raise PresetError(f"{label}画幅需要对应参考素材")
        else:
            for index, role in enumerate(("first", "last"), start=9001):
                if role not in media:
                    continue
                node_id = str(index)
                prompt[node_id] = {"class_type": "LoadImage", "inputs": {"image": media[role]}}
                input_name = self.manifest["frame_inputs"][role]
                prompt[target]["inputs"][input_name] = [node_id, 0]
                if reference_source is None:
                    reference_source = node_id
        if use_reference and reference_source is None:
            raise PresetError("参考图比例需要至少上传一张参考图")
        if use_reference:
            scale_node, size_node = "9003", "9004"
            prompt[scale_node] = {
                "class_type": reference["scale_class_type"],
                "inputs": {
                    "image": [reference_source, 0],
                    "upscale_method": reference["upscale_method"],
                    "megapixels": normalized["megapixels"],
                    "resolution_steps": reference["resolution_steps"],
                },
            }
            prompt[size_node] = {
                "class_type": reference["size_class_type"],
                "inputs": {"image": [scale_node, 0]},
            }
            prompt[target]["inputs"]["width"] = [size_node, 0]
            prompt[target]["inputs"]["height"] = [size_node, 1]
        return prompt

    def _add_reference_media(self, prompt: dict[str, Any], media: dict[str, str]) -> dict[str, str | None]:
        config = self.manifest["reference_media"]
        target = config["target_node"]
        image_roles = [role for role in ("first", "last") if role in media]
        image_roles.extend(sorted((role for role in media if role.startswith("image_")), key=lambda role: int(role[6:])))
        video_roles = sorted((role for role in media if role.startswith("video_")), key=lambda role: int(role[6:]))
        audio_roles = sorted((role for role in media if role.startswith("audio_")), key=lambda role: int(role[6:]))
        if len(image_roles) > config["images"]["max"] or len(video_roles) > config["videos"]["max"] or len(audio_roles) > config["audios"]["max"]:
            raise PresetError("参考素材数量超过工作流允许范围")
        reference_sources: dict[str, str | None] = {"image": None, "video": None}
        for index, role in enumerate(image_roles):
            node_id = str(9100 + index)
            prompt[node_id] = {"class_type": config["images"]["loader"], "inputs": {config["images"]["loader_input"]: media[role]}}
            prompt[target]["inputs"][f"{config['images']['input_prefix']}{index}"] = [node_id, 0]
            reference_sources["image"] = reference_sources["image"] or node_id
        for index, role in enumerate(video_roles):
            load_id, components_id = str(9200 + index), str(9300 + index)
            video = config["videos"]
            prompt[load_id] = {"class_type": video["loader"], "inputs": {video["loader_input"]: media[role]}}
            prompt[components_id] = {"class_type": video["components"], "inputs": {"video": [load_id, 0]}}
            prompt[target]["inputs"][f"{video['input_prefix']}{index}"] = [components_id, 0]
            prompt[target]["inputs"][f"{video['audio_input_prefix']}{index}"] = [components_id, 1]
            reference_sources["video"] = reference_sources["video"] or components_id
        for index, role in enumerate(audio_roles):
            node_id = str(9400 + index)
            audio = config["audios"]
            prompt[node_id] = {"class_type": audio["loader"], "inputs": {audio["loader_input"]: media[role]}}
            prompt[target]["inputs"][f"{audio['input_prefix']}{index}"] = [node_id, 0]
        return reference_sources


BUILTIN_WORKFLOW_DIR = Path(__file__).with_name("workflows")


def _load_presets_from(root: Path) -> dict[str, Preset]:
    presets: dict[str, Preset] = {}
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        directory = manifest_path.parent
        template_path = directory / manifest["workflow"]
        template = json.loads(template_path.read_text(encoding="utf-8"))
        preset = Preset(directory, manifest, template)
        _validate_manifest(preset)
        if preset.id in presets:
            raise PresetError(f"duplicate preset id: {preset.id}")
        presets[preset.id] = preset
    return presets


def load_presets(root: Path | None = None) -> dict[str, Preset]:
    presets = _load_presets_from(BUILTIN_WORKFLOW_DIR)
    if root is not None and root.is_dir() and root.resolve() != BUILTIN_WORKFLOW_DIR.resolve():
        presets.update(_load_presets_from(root))
    if not presets:
        raise PresetError("no workflow presets found")
    return presets


def _validate_manifest(preset: Preset) -> None:
    manifest, template = preset.manifest, preset.template
    if manifest.get("schema_version") != 1:
        raise PresetError("unsupported manifest schema")
    for key in ("id", "name", "workflow", "parameters", "locked", "dependencies", "output_node"):
        if key not in manifest:
            raise PresetError(f"manifest missing {key}")
    if manifest["output_node"] not in template:
        raise PresetError("output node is missing")
    for name, spec in manifest["parameters"].items():
        node = template.get(spec.get("node"))
        if not node or spec.get("input") not in node.get("inputs", {}):
            raise PresetError(f"parameter mapping is invalid: {name}")
    for assertion in manifest["locked"]:
        node = template.get(assertion["node"])
        if not node or node.get("class_type") != assertion["class_type"]:
            raise PresetError(f"locked node mismatch: {assertion['node']}")
        for key, value in assertion.get("inputs", {}).items():
            if node["inputs"].get(key) != value:
                raise PresetError(f"locked input mismatch: {assertion['node']}.{key}")
    reference = manifest.get("reference_aspect")
    if not isinstance(reference, dict) or reference.get("parameter_value") not in manifest["parameters"]["aspect_ratio"]["values"]:
        raise PresetError("reference aspect mapping is invalid")
    for key in ("legacy_parameter_value", "video_parameter_value"):
        value = reference.get(key)
        if value is not None and value not in manifest["parameters"]["aspect_ratio"]["values"]:
            raise PresetError("reference aspect mapping is invalid")
    if manifest.get("family") == "ref2va":
        media = manifest.get("reference_media")
        if not isinstance(media, dict) or media.get("target_node") not in template:
            raise PresetError("reference media mapping is invalid")
