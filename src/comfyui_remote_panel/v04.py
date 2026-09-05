from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from .image_resolution import (
    normalize_resolution_policy,
    normalize_target_megapixels,
    process_image,
)

SEED_POLICIES = {"randomize", "fixed", "increment"}
RISKY_IMAGE = re.compile(r"(?:mask|depth|control|canny|pose|normal|seg(?:ment)?|edge)", re.I)


def _seed_policy(value: Any, default: str = "randomize") -> str:
    policy = str(value or default).lower()
    if policy not in SEED_POLICIES:
        raise ValueError("Seed Policy 必须是 randomize / fixed / increment")
    return policy


def _slot_resolution_defaults(slot: dict[str, Any]) -> dict[str, Any]:
    semantic = str(slot.get("semantic") or slot.get("ui", {}).get("semantic") or "")
    confidence = str(slot.get("confidence") or slot.get("ui", {}).get("confidence") or "")
    allow_auto = slot.get("allow_auto")
    if allow_auto is None:
        allow_auto = semantic == "source_image" or (
            semantic == "reference_image" and confidence != "LOW"
        )
    policy = slot.get("resolution_policy")
    if policy is None:
        policy = "auto" if semantic == "reference_image" and allow_auto else "original"
    policy = normalize_resolution_policy(policy)
    if policy == "auto" and not allow_auto:
        policy = "original"
    target = normalize_target_megapixels(slot.get("target_megapixels", 1.0)) if policy == "auto" else None
    return {
        "resolution_policy": policy,
        "target_megapixels": target,
        "allow_auto": bool(allow_auto),
    }


def _media_resolution_for_role(preset: Any, role: str, overrides: dict[str, Any]) -> dict[str, Any]:
    media = preset.media_binding
    if media.get("type") == "slots":
        slot = media.get("slots", {}).get(role, {})
        defaults = _slot_resolution_defaults(slot) if isinstance(slot, dict) else {
            "resolution_policy": "original", "target_megapixels": None, "allow_auto": False
        }
    elif media.get("type") == "frame_pair":
        defaults = dict(media.get("resolution_defaults", {}).get(role) or {
            "resolution_policy": "auto", "target_megapixels": 1.0, "allow_auto": True
        })
    elif media.get("type") == "collection":
        defaults = dict(media.get("resolution_defaults", {}).get("image") or {
            "resolution_policy": "auto", "target_megapixels": 1.0, "allow_auto": True
        })
    else:
        defaults = {"resolution_policy": "original", "target_megapixels": None, "allow_auto": False}

    override = overrides.get(role)
    if override is None and role.startswith("image_"):
        override = overrides.get("image")
    if not isinstance(override, dict):
        override = {}
    allow_auto = bool(defaults.get("allow_auto"))
    policy = normalize_resolution_policy(
        override.get("policy", override.get("resolution_policy", defaults.get("resolution_policy", "original")))
    )
    if policy == "auto" and not allow_auto:
        policy = "original"
    target = None
    if policy == "auto":
        target = normalize_target_megapixels(
            override.get("target_megapixels", defaults.get("target_megapixels", 1.0))
        )
    return {
        "resolution_policy": policy,
        "target_megapixels": target,
        "allow_auto": allow_auto,
    }


def _parse_resolution_overrides(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("media_resolution 必须是 JSON 对象") from exc
    if not isinstance(value, dict):
        raise ValueError("media_resolution 必须是对象")
    return value


def _process_resolution(path: Path, policy: str, target: float | None) -> dict[str, Any]:
    return process_image(path, policy=policy, target_megapixels=target)


def _classify_error(job: dict[str, Any]) -> str:
    status = str(job.get("status") or "")
    code = str(job.get("error_code") or "")
    summary = str(job.get("error_summary") or "")
    text = f"{code} {summary}"
    if status in {"cancelled", "interrupted"} or "interrupted" in code:
        return "interrupted"
    if code == "output_missing" or "output missing" in text.lower():
        return "output_missing"
    if re.search(r"cuda.*out of memory|outofmemoryerror|cuda oom", text, re.I):
        return "cuda_oom"
    if re.search(r"(?:model|checkpoint|lora|vae).*(?:not found|missing|does not exist)|no such file", text, re.I):
        return "missing_model"
    if re.search(r"(?:node|class_type|custom node).*(?:not found|missing|unknown)|cannot execute because node", text, re.I):
        return "missing_node"
    if code in {"submission_uncertain", "upstream_temporarily_missing", "missing_upstream"}:
        return "comfyui_disconnected"
    if status == "failed" or code in {"execution_failed", "submission_unconfirmed"}:
        return "runtime_error"
    return "unknown"


def install() -> None:
    from . import db as db_module
    from . import preset as preset_module
    from . import workflow_analysis as analysis_module

    # ---- Database schema v6 / atomic increment allocation -----------------
    original_initialize = db_module.Database.initialize
    original_job_from_row = db_module.Database._job_from_row

    async def initialize_v04(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 6:
            return
        if version > 6:
            raise RuntimeError(f"unsupported database schema version: {version}")
        await original_initialize(self)
        async with self._lock:
            with self._connect() as connection:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version == 5:
                    connection.executescript(
                        """
                        ALTER TABLE jobs ADD COLUMN seed_policy TEXT NOT NULL DEFAULT 'fixed';
                        ALTER TABLE jobs ADD COLUMN seed_value TEXT;
                        ALTER TABLE jobs ADD COLUMN actual_seed TEXT;
                        ALTER TABLE jobs ADD COLUMN media_metadata_json TEXT;
                        UPDATE jobs
                           SET seed_policy = 'fixed',
                               seed_value = seed,
                               actual_seed = seed,
                               media_metadata_json = '{}';
                        CREATE TABLE seed_counters (
                            workflow_id TEXT NOT NULL,
                            seed_value TEXT NOT NULL,
                            next_offset INTEGER NOT NULL DEFAULT 0,
                            PRIMARY KEY(workflow_id, seed_value)
                        );
                        PRAGMA user_version = 6;
                        """
                    )
                    version = 6
                if version != 6:
                    raise RuntimeError(f"unsupported database schema version: {version}")

    async def create_job_v04(self, record: dict[str, Any], files: list[dict[str, Any]]) -> None:
        now = time.time()
        input_values = dict(record.get("input_values", {}))
        has_seed = bool(record.get("_has_seed"))
        policy = record.get("seed_policy") if has_seed else None
        seed_value = record.get("seed_value") if has_seed else None
        actual_seed: str | None = None

        async with self._lock:
            with self._connect() as connection:
                if has_seed:
                    policy = _seed_policy(policy, "randomize")
                    minimum = int(record.get("_seed_min", 0))
                    maximum = int(record.get("_seed_max", 18446744073709551615))
                    if policy == "randomize":
                        actual = minimum + secrets.randbelow(maximum - minimum + 1)
                    else:
                        if seed_value is None:
                            raise ValueError("固定或递增 Seed 需要基础 Seed")
                        base = int(seed_value)
                        if base < minimum or base > maximum:
                            raise ValueError("Seed 超出工作流允许范围")
                        if policy == "fixed":
                            actual = base
                        else:
                            workflow_id = str(record.get("workflow_id") or record["preset_id"])
                            row = connection.execute(
                                "SELECT next_offset FROM seed_counters WHERE workflow_id = ? AND seed_value = ?",
                                (workflow_id, str(base)),
                            ).fetchone()
                            offset = int(row[0]) if row else 0
                            actual = base + offset
                            if actual > maximum:
                                raise ValueError("递增 Seed 已超出工作流允许范围")
                            connection.execute(
                                """INSERT INTO seed_counters(workflow_id, seed_value, next_offset)
                                   VALUES (?, ?, ?)
                                   ON CONFLICT(workflow_id, seed_value)
                                   DO UPDATE SET next_offset = excluded.next_offset""",
                                (workflow_id, str(base), offset + 1),
                            )
                    actual_seed = str(actual)
                    input_values["seed"] = actual_seed
                    record["seed"] = actual_seed
                else:
                    record["seed"] = str(record.get("seed") or "0")

                record["actual_seed"] = actual_seed
                record["seed_policy"] = policy
                record["input_values"] = input_values
                connection.execute(
                    """INSERT INTO jobs (
                        id, preset_id, status, mode, prompt, duration_seconds,
                        aspect_ratio, megapixels, seed, scheduler, sampler, steps,
                        workflow_id, workflow_revision, workflow_snapshot_json,
                        input_values_json, is_test, seed_policy, seed_value,
                        actual_seed, media_metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record["id"], record["preset_id"], record["status"], record["mode"],
                        record.get("prompt", ""), record.get("duration_seconds", 0), record.get("aspect_ratio", "custom"),
                        record.get("megapixels", 0.0), str(record.get("seed", "0")), record.get("scheduler", "custom"),
                        record.get("sampler", "euler"), record.get("steps", 8),
                        record.get("workflow_id", record["preset_id"]), record.get("workflow_revision", 1),
                        json.dumps(record.get("workflow_snapshot"), ensure_ascii=False) if record.get("workflow_snapshot") else None,
                        json.dumps(input_values, ensure_ascii=False),
                        int(bool(record.get("is_test"))), policy or "fixed", seed_value,
                        actual_seed, json.dumps(record.get("media_metadata", {}), ensure_ascii=False),
                        now, now,
                    ),
                )
                for file in files:
                    connection.execute(
                        "INSERT INTO job_files(job_id, role, path, size_bytes) VALUES (?, ?, ?, ?)",
                        (record["id"], file["role"], str(file["path"]), file["size_bytes"]),
                    )
                    connection.execute(
                        """INSERT OR IGNORE INTO job_artifacts(
                            job_id, direction, binding_id, ordinal, path, kind, size_bytes
                        ) VALUES (?, 'input', ?, 0, ?, ?, ?)""",
                        (
                            record["id"], file["role"], str(file["path"]),
                            db_module._artifact_kind_for_role(file["role"]), file["size_bytes"],
                        ),
                    )

    def job_from_row_v04(self, row, files):
        item = original_job_from_row(self, row, files)
        raw = item.pop("media_metadata_json", None)
        try:
            item["media_metadata"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            item["media_metadata"] = {}
        if item.get("actual_seed") is None and item.get("seed") is not None:
            item["actual_seed"] = str(item["seed"])
        if item.get("seed_value") is None and item.get("actual_seed") is not None:
            item["seed_value"] = str(item["actual_seed"])
        return item

    db_module.Database.initialize = initialize_v04
    db_module.Database.create_job = create_job_v04
    db_module.Database._job_from_row = job_from_row_v04

    # ---- Workflow defaults / public metadata ------------------------------
    original_normalize_manifest = preset_module._normalize_manifest
    original_public_metadata = preset_module.Preset.public_metadata

    def normalize_manifest_v04(source: dict[str, Any]) -> dict[str, Any]:
        manifest = original_normalize_manifest(source)
        try:
            manifest["default_seed_policy"] = _seed_policy(
                manifest.get("default_seed_policy"), "randomize"
            )
        except ValueError as exc:
            raise preset_module.PresetError(str(exc)) from exc
        media = manifest.get("input_bindings", {}).get("media", {})
        media_type = media.get("type")
        if media_type == "slots":
            for role, slot in media.get("slots", {}).items():
                if not isinstance(slot, dict) or preset_module.FileStore.role_kind(role) != "image":
                    continue
                slot.update(_slot_resolution_defaults(slot))
        elif media_type == "frame_pair":
            defaults = media.setdefault("resolution_defaults", {})
            for role in media.get("roles", {}):
                defaults.setdefault(role, {
                    "resolution_policy": "auto",
                    "target_megapixels": 1.0,
                    "allow_auto": True,
                })
        elif media_type == "collection":
            media.setdefault("resolution_defaults", {}).setdefault("image", {
                "resolution_policy": "auto",
                "target_megapixels": 1.0,
                "allow_auto": True,
            })
        return manifest

    def public_metadata_v04(self):
        result = original_public_metadata(self)
        result["seed_policy"] = {
            "supported": "seed" in self.manifest.get("parameters", {}),
            "default": self.manifest.get("default_seed_policy", "randomize"),
            "values": ["randomize", "fixed", "increment"],
        }
        return result

    preset_module._normalize_manifest = normalize_manifest_v04
    preset_module.Preset.public_metadata = public_metadata_v04

    # ---- Workflow analysis: conservative image policy suggestions ---------
    original_analyze = analysis_module.analyze_workflow
    original_to_dict = analysis_module.WorkflowAnalysis.to_dict

    def analyze_v04(workflow: dict[str, Any], object_info: dict[str, Any] | None = None):
        result = original_analyze(workflow, object_info)
        consumers: dict[str, list[tuple[str, str]]] = {}
        for target_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            for input_name, value in (node.get("inputs") or {}).items():
                source = analysis_module.connection(value)
                if source:
                    consumers.setdefault(source[0], []).append((str(target_id), str(input_name)))

        policies: dict[str, dict[str, Any]] = {}
        for item in result.media_inputs:
            if item.kind != "image":
                continue
            targets = consumers.get(item.node, [])
            downstream = " ".join(
                f"{workflow.get(node_id, {}).get('class_type', '')} {input_name}"
                for node_id, input_name in targets
            )
            risk = bool(RISKY_IMAGE.search(f"{item.class_type} {item.input} {downstream}"))
            if item.semantic == "source_image":
                policy = "original"
                allow_auto = True
                note = "img2img 源图缩放可能同时改变生成尺寸"
            elif risk:
                policy = "original"
                allow_auto = False
                note = "像素级或控制类输入默认保持原图"
            elif targets:
                policy = "auto"
                allow_auto = True
                note = "普通参考图可安全使用自动缩放"
            else:
                policy = "original"
                allow_auto = False
                note = "用途无法可靠确认，默认保持原图"
            policies[item.id] = {
                "resolution_policy": policy,
                "target_megapixels": 1.0 if policy == "auto" else None,
                "allow_auto": allow_auto,
                "resolution_note": note,
            }
        result._v04_media_policies = policies
        return result

    def analysis_to_dict_v04(self):
        data = original_to_dict(self)
        policies = getattr(self, "_v04_media_policies", {})
        for item in data.get("media_inputs", []):
            item.update(policies.get(item.get("id"), {}))
        return data

    analysis_module.analyze_workflow = analyze_v04
    analysis_module.WorkflowAnalysis.to_dict = analysis_to_dict_v04

    # Import workflow_config only after analyze_workflow has been patched so its
    # module-level binding receives the v0.4 analyzer.
    from . import workflow_config as config_module

    original_build_definition = config_module.build_definition

    def build_definition_v04(workflow, remote_config, analysis=None):
        config = json.loads(json.dumps(remote_config))
        try:
            default_policy = _seed_policy(config.get("default_seed_policy"), "randomize")
        except ValueError as exc:
            raise preset_module.PresetError(str(exc)) from exc
        media = config.get("media")
        if isinstance(media, dict) and media.get("type") == "slots":
            for role, slot in media.get("slots", {}).items():
                if isinstance(slot, dict) and preset_module.FileStore.role_kind(role) == "image":
                    slot.update(_slot_resolution_defaults(slot))
        definition = original_build_definition(workflow, config, analysis)
        definition["manifest"]["default_seed_policy"] = default_policy
        return definition

    config_module.build_definition = build_definition_v04

    # ---- Job creation / retry / public reliability surface ----------------
    from . import jobs as jobs_module

    original_public_job = jobs_module.JobService.public_job

    async def create_v04(
        self, fields: dict[str, Any], uploaded: list[dict[str, Any]],
        job_id: str | None = None, *, is_test: bool = False,
    ) -> dict[str, Any]:
        job_id = job_id or jobs_module.new_job_id()
        preset_id = fields.get("preset_id") or "h3-fl2va-v4step600"
        preset = self.presets.get(preset_id)
        if preset is None:
            raise preset_module.PresetError("未知工作流预设")
        if not is_test:
            workflow = await self.db.get_workflow(str(preset_id))
            if workflow is not None and workflow.get("status") != "enabled":
                raise preset_module.PresetError("工作流已禁用")
        if not preset.available:
            await self.comfy.validate_preset(preset)
        if not preset.available:
            diagnostics = "；".join(preset.diagnostics[:3]) or "尚未完成在线检查"
            raise jobs_module.ComfyError("工作流预设当前不可用：" + diagnostics)

        effective_uploads = list(uploaded)
        copied: list[dict[str, Any]] = []
        persisted = False
        reservation = fields.get("_capacity_reservation")
        try:
            retry_source_id = fields.get("retry_source_id")
            if retry_source_id:
                source = await self.db.get_job(str(retry_source_id))
                if source is None or source["status"] not in jobs_module.TERMINAL_STATUSES:
                    raise preset_module.PresetError("原任务不存在或尚未结束，无法沿用参考图")
                keep_roles: set[str] | None = None
                if fields.get("retry_keep_roles") is not None:
                    try:
                        raw_keep_roles = json.loads(str(fields["retry_keep_roles"]))
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise preset_module.PresetError("retry_keep_roles 必须是 JSON 数组") from exc
                    if not isinstance(raw_keep_roles, list) or any(not isinstance(role, str) for role in raw_keep_roles):
                        raise preset_module.PresetError("retry_keep_roles 必须是 JSON 字符串数组")
                    keep_roles = set(raw_keep_roles)
                    source_roles = {
                        file["role"] for file in source["files"]
                        if self.files.role_kind(file["role"]) is not None
                    }
                    if not keep_roles <= source_roles:
                        raise preset_module.PresetError("retry_keep_roles 包含原任务不存在的素材槽位")
                supplied_roles = {item["role"] for item in effective_uploads}
                supplied_kinds = {self.files.role_kind(role) for role in supplied_roles}
                for file in source["files"]:
                    role = file["role"]
                    kind = self.files.role_kind(role)
                    compatible = preset.retry_role_compatible(role)
                    if keep_roles is not None:
                        should_copy = role in keep_roles
                    else:
                        replaced = (
                            role in supplied_roles
                            if preset.media_binding["type"] in {"frame_pair", "slots"}
                            else kind in supplied_kinds
                        )
                        should_copy = not replaced
                    if compatible and should_copy and role not in supplied_roles:
                        copied_file = await self.files.copy_input_async(
                            Path(file["path"]), job_id, file["role"], reservation=reservation
                        )
                        copied.append(copied_file)
                        effective_uploads.append(copied_file)

            roles = {file["role"] for file in effective_uploads}
            mode, allow_empty_prompt = preset.validate_media_roles(roles)

            seed_spec = preset.manifest.get("parameters", {}).get("seed")
            has_seed = isinstance(seed_spec, dict)
            explicit_seed = fields.get("seed") not in {None, ""}
            raw_policy = fields.get("seed_policy")
            if has_seed:
                policy = _seed_policy(
                    raw_policy,
                    "fixed" if raw_policy is None and explicit_seed
                    else preset.manifest.get("default_seed_policy", "randomize"),
                )
                seed_base = fields.get("seed_value", fields.get("seed"))
                parameter_fields = dict(fields)
                if policy in {"fixed", "increment"} and seed_base in {None, ""}:
                    seed_base = seed_spec.get("default", seed_spec.get("minimum", 0))
                parameter_fields["seed"] = seed_base if policy in {"fixed", "increment"} else None
            else:
                policy = None
                seed_base = None
                parameter_fields = dict(fields)

            normalized = preset.validate_parameters(
                parameter_fields, allow_empty_prompt=allow_empty_prompt
            )
            # Family routing and inference selection are persisted in the
            # existing JSON input payload; they are metadata, not workflow
            # parameters and therefore must survive the v0.4 seed layer.
            for metadata_key in (
                "_v047_prompt_backend",
                "_v047_inference_profile",
                "_v047_effective_inference_profile",
                "_v047_variant_model_overrides",
                "_v048_generation_mode",
                "_v048_prompt_backend",
                "_v048_inference_profile",
                "_v048_effective_inference_profile",
                "_v048_variant_model_overrides",
            ):
                if metadata_key in fields:
                    normalized[metadata_key] = fields[metadata_key]
            if has_seed:
                if policy in {"fixed", "increment"}:
                    seed_base = normalized.get("seed")
                else:
                    normalized["seed"] = None

            has_image = any(self.files.role_kind(role) == "image" for role in roles)
            if normalized.get("aspect_ratio") == "reference" and not has_image:
                raise preset_module.PresetError("参考图比例需要至少上传一张参考图")

            overrides = _parse_resolution_overrides(fields.get("media_resolution"))
            media_metadata: dict[str, Any] = {}
            for file in effective_uploads:
                role = file["role"]
                if self.files.role_kind(role) != "image":
                    continue
                settings = _media_resolution_for_role(preset, role, overrides)
                metadata = await self.files._run_blocking(
                    _process_resolution,
                    Path(file["path"]),
                    settings["resolution_policy"],
                    settings["target_megapixels"],
                )
                metadata["role"] = role
                metadata["allow_auto"] = settings["allow_auto"]
                file["size_bytes"] = Path(file["path"]).stat().st_size
                media_metadata[role] = metadata

            record = {
                "id": job_id,
                "preset_id": preset_id,
                "workflow_id": preset_id,
                "workflow_revision": preset.revision,
                "workflow_snapshot": preset.snapshot(),
                "input_values": normalized,
                "is_test": is_test,
                "status": "submitting",
                "mode": mode,
                "seed_policy": policy,
                "seed_value": str(seed_base) if seed_base not in {None, ""} else None,
                "media_metadata": media_metadata,
                "_has_seed": has_seed,
                "_seed_min": int(seed_spec.get("minimum", 0)) if has_seed else 0,
                "_seed_max": int(seed_spec.get("maximum", 18446744073709551615)) if has_seed else 0,
                **normalized,
            }
            await self.db.create_job(record, effective_uploads)
            persisted = True
            normalized = record["input_values"]
            media_names = {
                file["role"]: self.files.comfy_input_name(Path(file["path"]))
                for file in effective_uploads
            }
            variant_model_overrides = fields.get("_v048_variant_model_overrides")
            if not isinstance(variant_model_overrides, dict):
                variant_model_overrides = fields.get("_v047_variant_model_overrides")
            prompt = preset.build_prompt(
                normalized,
                job_id,
                media_names,
                variant_model_overrides if isinstance(variant_model_overrides, dict) else None,
            )
            await self.comfy.submit(job_id, prompt)
            _, job = await self.db.update_job_if_status(
                job_id, {"submitting"}, status="queued", stage="等待执行", queue_position=None
            )
        except (preset_module.PresetError, jobs_module.FileValidationError, ValueError):
            self.files.cleanup_untracked(copied)
            raise
        except Exception as exc:
            if not persisted:
                self.files.cleanup_untracked(copied)
                raise
            summary = jobs_module.safe_summary(exc, "任务提交失败")
            try:
                confirmed, job = await self._confirm_submission(job_id)
            except jobs_module.ComfyError:
                confirmed = False
                job = await self.db.get_job(job_id)
            if not confirmed:
                _, job = await self.db.update_job_if_status(
                    job_id, {"submitting"},
                    status="submitting",
                    stage="确认提交状态",
                    error_code="submission_uncertain",
                    error_summary=None,
                )
            jobs_module.log.warning(
                "ComfyUI submission response could not be trusted for job %s: %s",
                job_id, summary,
            )
        self.events.publish("job", self.public_job(job))
        return job

    async def retry_v04(self, job_id: str) -> dict[str, Any]:
        original = await self.db.get_job(job_id)
        if original is None:
            raise KeyError(job_id)
        if original["status"] not in jobs_module.TERMINAL_STATUSES:
            raise preset_module.PresetError("只有已结束任务可以重试")
        policy = original.get("seed_policy") or "fixed"
        seed_value = original.get("seed_value")
        values = dict(original.get("input_values", {}))
        if "seed" in values:
            values["seed"] = "" if policy == "randomize" else seed_value
        media_resolution = {
            role: {
                "policy": item.get("resolution_policy", "original"),
                "target_megapixels": item.get("target_megapixels"),
            }
            for role, item in (original.get("media_metadata") or {}).items()
        }
        return {
            "retry_source_id": original["id"],
            "preset_id": original["preset_id"],
            "prompt": original["prompt"],
            "duration_seconds": original["duration_seconds"],
            "aspect_ratio": original["aspect_ratio"],
            "megapixels": original["megapixels"],
            "seed": "" if policy == "randomize" else (seed_value or ""),
            "seed_policy": policy,
            "seed_value": seed_value,
            "actual_seed": original.get("actual_seed"),
            "media_resolution": media_resolution,
            "scheduler": original["scheduler"],
            "sampler": original["sampler"],
            "steps": original["steps"],
            "input_roles": [
                file["role"] for file in original["files"]
                if self.files.role_kind(file["role"]) is not None
            ],
            "retry_keep_roles": [
                file["role"] for file in original["files"]
                if self.files.role_kind(file["role"]) is not None
            ],
            "values": values,
        }

    def public_job_v04(self, job: dict[str, Any] | None):
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        actual = job.get("actual_seed")
        result["seed_policy"] = job.get("seed_policy")
        result["seed_value"] = job.get("seed_value")
        result["actual_seed"] = str(actual) if actual is not None else None
        if actual is not None:
            result["seed"] = str(actual)
        result["media_metadata"] = job.get("media_metadata") or {}
        result["media_resolution"] = {
            role: {
                "policy": item.get("resolution_policy", "original"),
                "target_megapixels": item.get("target_megapixels"),
            }
            for role, item in result["media_metadata"].items()
        }
        first_image = next(iter(result["media_metadata"].values()), None)
        if isinstance(first_image, dict):
            for key in (
                "source_width", "source_height", "effective_width", "effective_height",
                "resolution_policy", "target_megapixels",
            ):
                result[key] = first_image.get(key)
        result["task_state"] = {
            "submitting": "submitted",
            "queued": "queued",
            "running": "running",
            "succeeded": "completed",
            "failed": "failed",
            "cancelled": "interrupted",
            "interrupted": "interrupted",
            "output_missing": "failed",
        }.get(str(job.get("status")), str(job.get("status")))
        result["error_category"] = _classify_error(job)
        return result

    jobs_module.JobService.create = create_v04
    jobs_module.JobService.retry = retry_v04
    jobs_module.JobService.public_job = public_job_v04

    # ---- Panel / ComfyUI state separation ---------------------------------
    from . import metrics as metrics_module

    original_collect_once = metrics_module.MetricsService._collect_once

    async def collect_once_v04(self):
        snapshot = await original_collect_once(self)
        now = float(snapshot.get("timestamp") or time.time())
        snapshot["panel"] = {
            "online": True,
            "state": "online",
            "uptime_seconds": round(now - self.started_at),
        }
        comfy = snapshot.setdefault("comfyui", {})
        control_state = str(comfy.get("state") or "")
        comfy["control_state"] = control_state or None
        if comfy.get("online"):
            state = "online"
        elif control_state == "starting":
            state = "starting"
        elif getattr(self, "_comfy_failures", 0) < 3 and getattr(self, "_last_comfy_success_at", None) is None:
            state = "unknown"
        else:
            state = "offline"
        comfy["state"] = state
        return snapshot

    metrics_module.MetricsService._collect_once = collect_once_v04
