from __future__ import annotations

from typing import Any

from .preset import Preset, PresetError


_INSTALLED = False


def install_workflow_runtime() -> None:
    """Install narrow Generic Workflow runtime extensions.

    Keeping this migration shim isolated avoids changing H3's proven manifest
    implementation while Configurator 2.0 adds required slot semantics and a
    public capability profile. It can be removed once schema_version 3 folds
    these fields into Preset directly.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_validate_media_roles = Preset.validate_media_roles
    original_public_metadata = Preset.public_metadata

    def validate_media_roles(self: Preset, roles: set[str]) -> tuple[str, bool]:
        media = self.media_binding
        if media.get("type") == "slots":
            slots = media.get("slots", {})
            if roles - set(slots):
                raise PresetError("工作流收到了未声明的媒体槽位")
            required = {
                role for role, slot in slots.items()
                if isinstance(slot, dict) and (
                    slot.get("required") is True
                    or isinstance(slot.get("ui"), dict) and slot["ui"].get("optional") is False
                )
            }
            missing = sorted(required - roles)
            if missing:
                labels = [
                    str(slots[role].get("ui", {}).get("label") or role)
                    for role in missing
                ]
                raise PresetError(f"缺少必需素材：{'、'.join(labels)}")
            return ("纯文字" if not roles else f"{len(roles)} 个媒体输入"), False
        return original_validate_media_roles(self, roles)

    def public_metadata(self: Preset) -> dict[str, Any]:
        result = original_public_metadata(self)
        result["capability_profile"] = self.manifest.get("capability_profile", {})
        result["workflow_confidence"] = self.manifest.get("workflow_confidence")
        result["preflight"] = self.manifest.get("preflight", {})
        return result

    Preset.validate_media_roles = validate_media_roles
    Preset.public_metadata = public_metadata
