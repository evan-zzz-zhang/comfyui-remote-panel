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
        return self.manifest["output_bindings"][0]["node"]

    @property
    def revision(self) -> int:
        return int(self.manifest.get("revision", 1))

    @property
    def media_binding(self) -> dict[str, Any]:
        return self.manifest["input_bindings"]["media"]

    def snapshot(self) -> dict[str, Any]:
        return {"manifest": copy.deepcopy(self.manifest), "workflow": copy.deepcopy(self.template)}

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
        family = self.manifest.get("family", "generic")
        for name, spec in parameters.items():
            if family != "generic" and name in {"prompt", "seed"}:
                continue
            exposed[name] = {
                key: copy.deepcopy(spec[key])
                for key in ("type", "minimum", "maximum", "step", "default", "values", "ui")
                if key in spec
            }
        media = self.manifest.get("reference_media")
        public_media = None if not media else {
            kind: {"max": media[kind]["max"]} for kind in ("images", "videos", "audios")
        }
        return {
            "id": self.id,
            "revision": self.revision,
            "name": self.manifest["name"],
            "family": family,
            "description": self.manifest.get("description", ""),
            "available": self.available,
            "diagnostics": self.diagnostics,
            "parameters": exposed,
            "reference_media": public_media,
            "input_bindings": copy.deepcopy(self.manifest["input_bindings"]),
            "output_bindings": copy.deepcopy(self.manifest["output_bindings"]),
        }

    def validate_media_roles(self, roles: set[str]) -> tuple[str, bool]:
        media = self.media_binding
        if media["type"] == "frame_pair":
            allowed = set(media["roles"])
            if roles - allowed:
                raise PresetError("工作流收到了未声明的媒体槽位")
            labels = media.get("mode_labels", {})
            key = "+".join(role for role in media["roles"] if role in roles)
            return labels.get(key, "纯文字" if not roles else f"{len(roles)} 个输入"), bool(roles)
        if media["type"] == "collection":
            counts = {
                kind: sum(FileStore.role_kind(role) == kind for role in roles)
                for kind in ("image", "video", "audio")
            }
            if any(FileStore.role_kind(role) is None for role in roles):
                raise PresetError("工作流收到了未声明的媒体槽位")
            for kind, count in counts.items():
                if count > media["kinds"][f"{kind}s"]["max"]:
                    raise PresetError("参考素材数量超过工作流允许范围")
            mode = " · ".join(
                f"{counts[kind]}{label}" for kind, label in (("image", "图"), ("video", "视频"), ("audio", "音频"))
                if counts[kind]
            ) or "纯文字"
            return mode, False
        if media["type"] == "slots":
            if roles - set(media.get("slots", {})):
                raise PresetError("工作流收到了未声明的媒体槽位")
            return ("纯文字" if not roles else f"{len(roles)} 个媒体输入"), False
        if roles:
            raise PresetError("该工作流不接受媒体输入")
        return "纯文字", False

    def retry_role_compatible(self, role: str) -> bool:
        media = self.media_binding
        if media["type"] == "frame_pair":
            return role in media.get("roles", {})
        if media["type"] == "slots":
            return role in media.get("slots", {})
        return FileStore.role_kind(role) is not None

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
            elif spec["type"] == "string":
                if not isinstance(value, str):
                    raise PresetError(f"{name} 必须是文本")
            elif spec["type"] == "boolean":
                if not isinstance(value, bool):
                    raise PresetError(f"{name} 必须是布尔值")
            elif spec["type"] == "enum":
                if value not in spec["values"]:
                    raise PresetError(f"不支持的 {name}")
            if "minimum" in spec and value < spec["minimum"]:
                raise PresetError(f"{name} 低于允许范围")
            if "maximum" in spec and value > spec["maximum"]:
                raise PresetError(f"{name} 超出允许范围")
            result[name] = value
        return result

    def _apply_variant_model_overrides(
        self,
        prompt: dict[str, Any],
        effective_profile: Any,
        variant_model_overrides: dict[str, dict[str, str]] | None = None,
    ) -> None:
        from .inference_profile import model_variant_dependencies, normalize_inference_profile

        profile = normalize_inference_profile(effective_profile)
        model_profile = self.manifest.get("model_profile", {})
        main_model = model_profile.get("main_model", {}) if isinstance(model_profile, dict) else {}
        current = normalize_inference_profile(main_model.get("current", "int8"))
        if profile == current:
            return
        runtime_overrides = variant_model_overrides or {}
        for dependency in model_variant_dependencies(self, profile):
            node_id = str(dependency.get("node") or "")
            input_name = str(dependency.get("input") or "")
            model_name = dependency.get("name")
            runtime_name = runtime_overrides.get(node_id, {}).get(input_name, model_name)
            if node_id and input_name and runtime_name and node_id in prompt:
                prompt[node_id]["inputs"][input_name] = str(runtime_name)

    def build_prompt(
        self,
        values: dict[str, Any],
        job_id: str,
        media: dict[str, str],
        variant_model_overrides: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        _, allow_empty_prompt = self.validate_media_roles(set(media))
        normalized = self.validate_parameters(values, allow_empty_prompt=allow_empty_prompt)
        reference = self.manifest.get("reference_aspect", {})
        aspect_value = normalized.get("aspect_ratio")
        reference_values = {reference.get("parameter_value"), reference.get("legacy_parameter_value", "reference"), reference.get("video_parameter_value")}
        use_reference = aspect_value in reference_values
        prompt = copy.deepcopy(self.template)
        for node_id, inputs in self.model_overrides.items():
            prompt[node_id]["inputs"].update(inputs)
        effective_profile = values.get("_v047_effective_inference_profile")
        if not effective_profile:
            effective_profile = values.get("_v048_effective_inference_profile")
        if effective_profile:
            self._apply_variant_model_overrides(prompt, effective_profile, variant_model_overrides)
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
        if "filename_prefix" in prompt[self.output_node].get("inputs", {}):
            prompt[self.output_node]["inputs"]["filename_prefix"] = f"h3_remote/{output_key}"
        reference_source: str | None = None
        media_binding = self.media_binding
        if media_binding["type"] == "none":
            return prompt
        if media_binding["type"] == "slots":
            for role, filename in media.items():
                slot = media_binding["slots"][role]
                prompt[str(slot["node"])]["inputs"][slot["input"]] = filename
            return prompt
        target = media_binding["target_node"]
        if media_binding["type"] == "collection":
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
                input_name = media_binding["roles"][role]
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
        config = self.media_binding
        target = config["target_node"]
        image_roles = [role for role in ("first", "last") if role in media]
        image_roles.extend(sorted((role for role in media if role.startswith("image_")), key=lambda role: int(role[6:])))
        video_roles = sorted((role for role in media if role.startswith("video_")), key=lambda role: int(role[6:]))
        audio_roles = sorted((role for role in media if role.startswith("audio_")), key=lambda role: int(role[6:]))
        kinds = config["kinds"]
        if len(image_roles) > kinds["images"]["max"] or len(video_roles) > kinds["videos"]["max"] or len(audio_roles) > kinds["audios"]["max"]:
            raise PresetError("参考素材数量超过工作流允许范围")
        reference_sources: dict[str, str | None] = {"image": None, "video": None}
        for index, role in enumerate(image_roles):
            node_id = str(9100 + index)
            prompt[node_id] = {"class_type": kinds["images"]["loader"], "inputs": {kinds["images"]["loader_input"]: media[role]}}
            prompt[target]["inputs"][f"{kinds['images']['input_prefix']}{index}"] = [node_id, 0]
            reference_sources["image"] = reference_sources["image"] or node_id
        for index, role in enumerate(video_roles):
            load_id, components_id = str(9200 + index), str(9300 + index)
            video = kinds["videos"]
            prompt[load_id] = {"class_type": video["loader"], "inputs": {video["loader_input"]: media[role]}}
            prompt[components_id] = {"class_type": video["components"], "inputs": {"video": [load_id, 0]}}
            prompt[target]["inputs"][f"{video['input_prefix']}{index}"] = [components_id, 0]
            prompt[target]["inputs"][f"{video['audio_input_prefix']}{index}"] = [components_id, 1]
            reference_sources["video"] = reference_sources["video"] or components_id
        for index, role in enumerate(audio_roles):
            node_id = str(9400 + index)
            audio = kinds["audios"]
            prompt[node_id] = {"class_type": audio["loader"], "inputs": {audio["loader_input"]: media[role]}}
            prompt[target]["inputs"][f"{audio['input_prefix']}{index}"] = [node_id, 0]
        return reference_sources


BUILTIN_WORKFLOW_DIR = Path(__file__).with_name("workflows")


def _load_presets_from(root: Path) -> dict[str, Preset]:
    presets: dict[str, Preset] = {}
    # Built-in workflow assets may be grouped by family/generation/backend.
    # External flat directories remain supported because rglob also includes
    # the established ``workflows/*/manifest.json`` layout.
    for manifest_path in sorted(root.rglob("manifest.json")):
        manifest = _normalize_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
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


def preset_from_definition(definition: dict[str, Any], directory: Path | None = None) -> Preset:
    if not isinstance(definition, dict) or not isinstance(definition.get("manifest"), dict):
        raise PresetError("workflow definition must contain a manifest")
    if not isinstance(definition.get("workflow"), dict):
        raise PresetError("workflow definition must contain an API workflow")
    preset = Preset(
        directory or Path("."), _normalize_manifest(definition["manifest"]),
        copy.deepcopy(definition["workflow"]),
    )
    _validate_manifest(preset)
    return preset


def _validate_manifest(preset: Preset) -> None:
    manifest, template = preset.manifest, preset.template
    if manifest.get("schema_version") != 2:
        raise PresetError("unsupported manifest schema")
    for key in ("id", "name", "workflow", "parameters", "locked", "dependencies", "output_node"):
        if key not in manifest:
            raise PresetError(f"manifest missing {key}")
    if manifest["output_node"] not in template:
        raise PresetError("output node is missing")
    outputs = manifest.get("output_bindings")
    if not isinstance(outputs, list) or not outputs:
        raise PresetError("output bindings are missing")
    for output in outputs:
        if (
            not isinstance(output, dict) or not isinstance(output.get("id"), str)
            or str(output.get("node")) not in template
            or output.get("kind") not in {"image", "video", "audio", "file"}
        ):
            raise PresetError("output binding is invalid")
    for name, spec in manifest["parameters"].items():
        node = template.get(spec.get("node"))
        if not node or spec.get("input") not in node.get("inputs", {}):
            raise PresetError(f"parameter mapping is invalid: {name}")
        if spec.get("type") not in {"string", "integer", "number", "boolean", "enum"}:
            raise PresetError(f"parameter type is invalid: {name}")
    for assertion in manifest["locked"]:
        node = template.get(assertion["node"])
        if not node or node.get("class_type") != assertion["class_type"]:
            raise PresetError(f"locked node mismatch: {assertion['node']}")
        for key, value in assertion.get("inputs", {}).items():
            if node["inputs"].get(key) != value:
                raise PresetError(f"locked input mismatch: {assertion['node']}.{key}")
    model_profile = manifest.get("model_profile", {})
    main_model = model_profile.get("main_model", {}) if isinstance(model_profile, dict) else {}
    variants = main_model.get("variants", {}) if isinstance(main_model, dict) else {}
    if isinstance(variants, dict):
        for profile, variant in variants.items():
            if not isinstance(variant, dict):
                raise PresetError(f"模型配置变体无效：{profile}")
            dependencies = variant.get("dependencies", [])
            if variant.get("available") is True and not variant.get("inherits_current") and not dependencies:
                raise PresetError(f"模型配置变体缺少模型绑定：{profile}")
            if not isinstance(dependencies, list):
                raise PresetError(f"模型配置变体依赖无效：{profile}")
            for dependency in dependencies:
                if not isinstance(dependency, dict):
                    raise PresetError(f"模型配置变体依赖无效：{profile}")
                node_id = str(dependency.get("node") or "")
                input_name = str(dependency.get("input") or "")
                if (
                    not dependency.get("category")
                    or not dependency.get("name")
                    or not node_id
                    or not input_name
                    or node_id not in template
                    or input_name not in template[node_id].get("inputs", {})
                ):
                    raise PresetError(f"模型配置变体绑定无效：{profile}")
    reference = manifest.get("reference_aspect")
    if "aspect_ratio" in manifest["parameters"]:
        if not isinstance(reference, dict) or reference.get("parameter_value") not in manifest["parameters"]["aspect_ratio"]["values"]:
            raise PresetError("reference aspect mapping is invalid")
        for key in ("legacy_parameter_value", "video_parameter_value"):
            value = reference.get(key)
            if value is not None and value not in manifest["parameters"]["aspect_ratio"]["values"]:
                raise PresetError("reference aspect mapping is invalid")
    media = manifest.get("input_bindings", {}).get("media")
    if not isinstance(media, dict) or media.get("type") not in {"none", "frame_pair", "collection", "slots"}:
        raise PresetError("media input binding is invalid")
    if media.get("type") in {"frame_pair", "collection"} and media.get("target_node") not in template:
        raise PresetError("media target node is invalid")
    if media.get("type") == "slots":
        for role, slot in media.get("slots", {}).items():
            node = template.get(str(slot.get("node"))) if isinstance(slot, dict) else None
            if FileStore.role_kind(role) is None or not node or slot.get("input") not in node.get("inputs", {}):
                raise PresetError(f"media slot is invalid: {role}")


def _normalize_manifest(source: dict[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(source)
    if manifest.get("schema_version") not in {1, 2}:
        raise PresetError("unsupported manifest schema")
    manifest["schema_version"] = 2
    manifest.setdefault("revision", 1)
    bindings = manifest.setdefault("input_bindings", {})
    bindings.setdefault("values", copy.deepcopy(manifest.get("parameters", {})))
    if "media" not in bindings:
        if manifest.get("reference_media"):
            legacy = copy.deepcopy(manifest["reference_media"])
            bindings["media"] = {
                "type": "collection", "target_node": legacy["target_node"],
                "kinds": {key: legacy[key] for key in ("images", "videos", "audios")},
            }
        elif manifest.get("frame_inputs"):
            frames = manifest["frame_inputs"]
            bindings["media"] = {
                "type": "frame_pair", "target_node": frames["target_node"],
                "roles": {key: frames[key] for key in ("first", "last")},
                "mode_labels": copy.deepcopy(manifest.get("mode_labels", {})),
            }
        else:
            bindings["media"] = {"type": "none"}
    manifest.setdefault("output_bindings", [{
        "id": "primary", "node": manifest["output_node"], "kind": "video",
        "history_keys": ["videos", "video", "files", "images"], "primary": True,
    }])
    return manifest
