from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .preset import Preset
from .workflow_analysis import Severity, advertised_inputs, classify_unknown_input, connection


log = logging.getLogger(__name__)


class ComfyError(RuntimeError):
    pass


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.split("."):
        digits = "".join(char for char in part if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple((parts + [0, 0, 0])[:3])


class ComfyClient:
    def __init__(self, base_url: str, minimum_version: str, client_id: str):
        self.base_url = base_url.rstrip("/")
        self.minimum_version = minimum_version
        self.client_id = client_id
        self.session: aiohttp.ClientSession | None = None
        self.capabilities_verified = False
        self._validation_lock = asyncio.Lock()

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=10, connect=3)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None:
            raise RuntimeError("Comfy client is not started")
        return self.session

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._session().request(method, self.base_url + path, **kwargs) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400:
                    raise ComfyError(self._safe_error(payload, response.status))
                return payload
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise ComfyError("ComfyUI 暂时无法连接") from exc

    @staticmethod
    def _safe_error(payload: Any, status: int) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("type")
                if isinstance(message, str):
                    return f"ComfyUI 拒绝请求：{message[:300]}"
            if isinstance(error, str):
                return f"ComfyUI 拒绝请求：{error[:300]}"
        return f"ComfyUI 请求失败（HTTP {status}）"

    async def system_stats(self) -> dict[str, Any]:
        return await self._json("GET", "/system_stats")

    async def check_version(self, stats: dict[str, Any] | None = None) -> str:
        stats = stats if stats is not None else await self.system_stats()
        version = str(stats.get("system", {}).get("comfyui_version", "0"))
        if _version_tuple(version) < _version_tuple(self.minimum_version):
            raise ComfyError(f"ComfyUI {version} 过旧，需要 {self.minimum_version} 或更高版本")
        if not self.capabilities_verified:
            result = await self._json("POST", f"/api/jobs/{uuid.uuid4()}/cancel", json={})
            if not isinstance(result, dict) or result.get("cancelled") is not False:
                raise ComfyError("ComfyUI 不支持安全的定向任务取消")
            self.capabilities_verified = True
        return version

    async def validate_preset(self, preset: Preset) -> list[str]:
        return (await self.validate_presets([preset]))[preset.id]

    async def validate_presets(
        self, presets: list[Preset], stats: dict[str, Any] | None = None
    ) -> dict[str, list[str]]:
        """Validate only incompatibilities that can actually prevent execution.

        Configurator 2.0 deliberately distinguishes runtime inputs from frontend
        helper/legacy literal fields. A JSON literal that is absent from the
        current `/object_info` schema is retained and reported by workflow
        preflight as WARN; it no longer makes the workflow unavailable. Missing
        connected inputs remain FAIL because they change graph execution.
        """
        async with self._validation_lock:
            node_cache: dict[str, Any] = {}
            model_cache: dict[str, Any] = {}
            results: dict[str, tuple[list[str], dict[str, dict[str, str]]]] = {}
            try:
                await self.check_version(stats)
            except ComfyError as exc:
                message = str(exc)
                for preset in presets:
                    results[preset.id] = ([message], {})
            else:
                for preset in presets:
                    diagnostics: list[str] = []
                    overrides: dict[str, dict[str, str]] = {}
                    try:
                        reference = preset.manifest.get("reference_aspect", {})
                        dynamic_inputs = {
                            str(reference.get("scale_class_type")): {"image", "upscale_method", "megapixels", "resolution_steps"},
                            str(reference.get("size_class_type")): {"image"},
                        }
                        media = preset.manifest.get("reference_media") or {}
                        for section in ("images", "videos", "audios"):
                            spec = media.get(section)
                            if isinstance(spec, dict) and spec.get("loader") and spec.get("loader_input"):
                                dynamic_inputs.setdefault(str(spec["loader"]), set()).add(str(spec["loader_input"]))
                        video_spec = media.get("videos")
                        if isinstance(video_spec, dict) and video_spec.get("components"):
                            dynamic_inputs.setdefault(str(video_spec["components"]), set()).add("video")
                        dynamic_inputs.pop("None", None)

                        node_types = sorted(
                            {node["class_type"] for node in preset.template.values()}
                            | {"LoadImage"}
                            | set(dynamic_inputs)
                        )
                        for node_type in node_types:
                            if node_type not in node_cache:
                                try:
                                    node_cache[node_type] = await self._json("GET", f"/object_info/{node_type}")
                                except ComfyError as exc:
                                    node_cache[node_type] = exc
                            info = node_cache[node_type]
                            if isinstance(info, ComfyError):
                                raise info
                            if not isinstance(info, dict) or node_type not in info:
                                diagnostics.append(f"缺少节点：{node_type}")
                                continue

                            advertised = advertised_inputs({node_type: info}, node_type)
                            node_info = info[node_type]
                            if isinstance(node_info, dict):
                                for group in node_info.get("input_order", {}).values():
                                    if isinstance(group, list):
                                        advertised.update(str(value) for value in group)
                            if not advertised:
                                # Some test doubles / old custom nodes expose no
                                # field list. There is not enough evidence to call
                                # every literal input incompatible.
                                continue

                            expected: dict[str, bool] = {}
                            for node in preset.template.values():
                                if node["class_type"] != node_type:
                                    continue
                                for input_name, value in node.get("inputs", {}).items():
                                    if "." in input_name:
                                        continue
                                    expected[input_name] = expected.get(input_name, False) or connection(value) is not None
                            for input_name in dynamic_inputs.get(node_type, set()):
                                expected[input_name] = True

                            for missing in sorted(set(expected) - advertised):
                                severity = classify_unknown_input(node_type, missing, connected=expected[missing])
                                if severity == Severity.FAIL:
                                    diagnostics.append(f"节点输入不兼容：{node_type}.{missing}")
                                # WARN is intentionally not added to `diagnostics`:
                                # `preset.available` must only reflect blockers.
                                # The persisted preflight retains the warning.

                        for dependency in preset.manifest["dependencies"]:
                            category = dependency["category"]
                            if category not in model_cache:
                                try:
                                    models = await self._json("GET", f"/models/{category}")
                                    model_cache[category] = {
                                        str(value).replace("\\", "/"): str(value) for value in models
                                    }
                                except ComfyError as exc:
                                    model_cache[category] = exc
                            models = model_cache[category]
                            if isinstance(models, ComfyError):
                                raise models
                            expected_name = dependency["name"].replace("\\", "/")
                            if expected_name not in models:
                                diagnostics.append(f"缺少模型：{dependency['name']}")
                            elif dependency.get("node") and dependency.get("input"):
                                overrides.setdefault(str(dependency["node"]), {})[
                                    str(dependency["input"])
                                ] = models[expected_name]
                    except ComfyError as exc:
                        diagnostics.append(str(exc))
                    results[preset.id] = (diagnostics, overrides)

            for preset in presets:
                diagnostics, overrides = results[preset.id]
                preset.diagnostics = diagnostics
                preset.model_overrides = overrides
                preset.available = not diagnostics
            return {preset_id: diagnostics for preset_id, (diagnostics, _) in results.items()}

    async def submit(self, prompt_id: str, prompt: dict[str, Any]) -> dict[str, Any]:
        result = await self._json(
            "POST",
            "/prompt",
            json={"prompt": prompt, "prompt_id": prompt_id, "client_id": self.client_id},
        )
        if result.get("prompt_id") != prompt_id:
            raise ComfyError("ComfyUI 未接受面板指定的任务 ID")
        return result

    async def cancel(self, prompt_id: str) -> bool:
        result = await self._json("POST", f"/api/jobs/{prompt_id}/cancel", json={})
        return bool(result.get("cancelled"))

    async def queue(self) -> dict[str, Any]:
        return await self._json("GET", "/queue")

    async def history(self, prompt_id: str) -> dict[str, Any]:
        return await self._json("GET", f"/history/{prompt_id}")

    async def object_info(self, node_type: str) -> dict[str, Any]:
        return await self._json("GET", f"/object_info/{node_type}")

    async def websocket_events(self) -> AsyncIterator[dict[str, Any]]:
        parsed = urlsplit(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = urlunsplit((scheme, parsed.netloc, parsed.path + "/ws", f"clientId={self.client_id}", ""))
        try:
            timeout = aiohttp.ClientWSTimeout(ws_receive=45, ws_close=10)
            async with self._session().ws_connect(ws_url, heartbeat=20, timeout=timeout) as socket:
                async for message in socket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            event = json.loads(message.data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict):
                            yield event
                    elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                        break
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise ComfyError("ComfyUI WebSocket 已断开") from exc
