from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .preset import Preset


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

    async def check_version(self) -> str:
        stats = await self.system_stats()
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
        diagnostics: list[str] = []
        preset.model_overrides = {}
        try:
            await self.check_version()
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
                info = await self._json("GET", f"/object_info/{node_type}")
                if not isinstance(info, dict) or node_type not in info:
                    diagnostics.append(f"缺少节点：{node_type}")
                    continue
                node_info = info[node_type]
                advertised: set[str] = set()
                if isinstance(node_info, dict):
                    for group in node_info.get("input", {}).values():
                        if isinstance(group, dict):
                            advertised.update(group)
                    for group in node_info.get("input_order", {}).values():
                        if isinstance(group, list):
                            advertised.update(str(value) for value in group)
                if advertised:
                    expected = {
                        input_name
                        for node in preset.template.values()
                        if node["class_type"] == node_type
                        for input_name in node.get("inputs", {})
                        if "." not in input_name
                    }
                    expected.update(dynamic_inputs.get(node_type, set()))
                    for missing in sorted(expected - advertised):
                        diagnostics.append(f"节点输入不兼容：{node_type}.{missing}")
            models_by_category: dict[str, dict[str, str]] = {}
            for dependency in preset.manifest["dependencies"]:
                category = dependency["category"]
                if category not in models_by_category:
                    models = await self._json("GET", f"/models/{category}")
                    models_by_category[category] = {
                        str(value).replace("\\", "/"): str(value) for value in models
                    }
                expected = dependency["name"].replace("\\", "/")
                if expected not in models_by_category[category]:
                    diagnostics.append(f"缺少模型：{dependency['name']}")
                elif dependency.get("node") and dependency.get("input"):
                    preset.model_overrides.setdefault(str(dependency["node"]), {})[
                        str(dependency["input"])
                    ] = models_by_category[category][expected]
        except ComfyError as exc:
            diagnostics.append(str(exc))
        preset.diagnostics = diagnostics
        preset.available = not diagnostics
        return diagnostics

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
