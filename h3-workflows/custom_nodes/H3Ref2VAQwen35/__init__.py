from __future__ import annotations

import copy
import gc
import json
import logging
import math
import os
import re
from pathlib import Path

import torch

import comfy.model_management
import folder_paths
from comfy.cli_args import args
from comfy_api.latest import ComfyExtension, io, ui, Types
from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo
from .ref2va_contract import (
    REF2VA_FPS,
    REF2VA_MAX_DURATION,
    REF2VA_MIN_DURATION,
    audio_duration as _contract_audio_duration,
    h3_length as _contract_h3_length,
    normalize_reference_video as _contract_normalize_reference_video,
    validate_normalize_proof,
    validate_synced_audio,
)

FPS = int(REF2VA_FPS)
MAX_QWEN_VIDEO_FRAMES = 12
WRITER_VERSION = "ref2va-qwen35-reference-standardization-v1"
LAST_QWEN_REQUEST_CAPTURE = []

PERSIST_RAW_REQUEST_NODE_ID = 180
PERSIST_STANDARDIZED_PROMPT_NODE_ID = 181
PERSIST_FINAL_PROMPT_NODE_ID = 182
PERSIST_TAG_MAP_NODE_ID = 184
PERSIST_ROLE_MAP_NODE_ID = 185
PERSIST_ACTUAL_SIZE_NODE_ID = 186
PERSIST_FACT_REPORTS_NODE_ID = 188
PERSIST_VALIDATOR_NODE_ID = 189

PICTURE_DOMAINS = [
    "identity", "face", "hair", "body_appearance", "clothing", "pose", "expression",
    "environment", "lighting", "composition", "visual_style", "props", "text_graphics",
]
VIDEO_DOMAINS = [
    "performer_identity", "face_hair", "clothing", "environment", "lighting", "visual_style",
    "motion", "pose_sequence", "camera_movement", "cut_structure", "pacing_rhythm",
    "composition", "props", "text_graphics",
]
AUDIO_DOMAINS = [
    "full_signal", "voice_timbre", "voice_delivery", "dialogue_content", "lyrics_content",
    "music_style", "beat_rhythm", "sound_effect_texture", "ambience",
]
OFFICIAL_TASK_TYPES = {
    "keyframe completion", "reference generation", "video editing", "video continuation",
    "audio reuse", "audio reference",
}

ROLE_EVIDENCE_TERMS = {
    "identity": ("identity", "人物身份", "身份", "人物外貌", "角色外貌"),
    "face": ("face", "脸", "面部", "五官", "人物外貌", "角色外貌", "appearance"),
    "hair": ("hair", "头发", "发型", "人物外貌", "角色外貌", "appearance"),
    "body_appearance": ("body", "身体", "体型", "身材", "外貌", "appearance"),
    "clothing": ("clothing", "服装", "衣服", "穿着", "装束", "服饰"),
    "pose": ("pose", "姿态", "姿势"),
    "expression": ("expression", "表情"),
    "environment": ("environment", "环境", "场景", "地点", "背景"),
    "lighting": ("lighting", "光线", "灯光", "照明"),
    "composition": ("composition", "构图", "画面布局"),
    "visual_style": ("visual style", "style", "风格", "视觉风格", "画风"),
    "props": ("props", "道具", "物件"),
    "text_graphics": ("text", "文字", "字幕", "标识", "图形"),
    "performer_identity": ("performer", "identity", "人物身份", "身份", "人物", "角色", "外貌"),
    "face_hair": ("face", "hair", "脸", "面部", "头发", "发型"),
    "motion": ("motion", "动作", "运动", "动态"),
    "pose_sequence": ("pose", "姿态", "姿势", "动作", "动作序列"),
    "camera_movement": ("camera", "镜头", "运镜", "摄影机"),
    "cut_structure": ("cut", "剪辑", "转场", "切镜"),
    "pacing_rhythm": ("pacing", "rhythm", "节奏", "韵律"),
    "full_signal": ("full signal", "原始声音", "原声音轨", "完整音频"),
    "voice_timbre": ("voice", "音色", "嗓音"),
    "voice_delivery": ("delivery", "语气", "演唱方式", "说话方式"),
    "dialogue_content": ("dialogue", "对白", "台词", "说话内容"),
    "lyrics_content": ("lyrics", "歌词"),
    "music_style": ("music", "音乐", "曲风"),
    "beat_rhythm": ("beat", "节拍", "节奏"),
    "sound_effect_texture": ("sound effect", "音效"),
    "ambience": ("ambience", "环境声", "氛围声"),
}

EXPLICIT_TASK_EVIDENCE = {
    "video editing": (
        "video editing", "edit the source video", "edit the reference video",
        "编辑参考视频", "修改参考视频", "在原视频上", "剪辑原视频",
    ),
    "video continuation": (
        "video continuation", "continue the source video", "continue the reference video",
        "续接", "续写", "延续", "继续参考视频", "扩展参考视频", "接着参考视频",
    ),
    "audio reuse": (
        "audio reuse", "reuse the original audio", "retain the original audio",
        "保留原始声音", "保留原声音轨", "保留原始音频", "保留原音轨",
        "保留它的原始声音", "保留它的原始音频", "它的原始声音", "它的原始音频",
        "复用原始声音", "复用原始音频", "沿用原始声音", "沿用原音频",
        "使用原始声音", "使用原始音频",
    ),
    "audio reference": (
        "audio reference", "use the audio as a reference", "声音参考", "音频参考",
        "参考音色", "参考声音", "参考音频",
    ),
    "keyframe completion": (
        "keyframe completion", "complete the keyframe", "首帧补全", "尾帧补全",
        "关键帧补全", "关键帧生成",
    ),
}

# Visual fact models sometimes place a location, light, or outfit detail in a
# motion bucket. Remove those cross-domain facts when the corresponding domain
# was not authorized by the user's clause.
CROSS_DOMAIN_FACT_CUES = {
    "environment": (
        "background", "setting", "location", "scene", "room", "street", "beach",
        "water", "sky", "indoor", "outdoor", "背景", "环境", "场景", "地点", "房间",
        "街道", "海滩", "水面", "天空", "室内", "室外",
    ),
    "lighting": ("lighting", "illumination", "light", "shadow", "灯光", "光线", "照明", "阴影"),
    "clothing": ("clothing", "outfit", "wearing", "dress", "shirt", "pants", "服装", "衣服", "穿着", "装束"),
    "visual_style": ("visual style", "style", "anime", "cinematic", "cel-shaded", "风格", "画风", "动漫", "电影感"),
    "props": ("prop", "holding", "carrying", "道具", "手持", "携带"),
    "composition": ("composition", "framing", "close-up", "full-body", "构图", "景别", "取景"),
    "text_graphics": ("text", "subtitle", "logo", "signage", "文字", "字幕", "标识", "招牌"),
}


def _evidence_domains(evidence: str, domains: list[str]) -> set[str]:
    text = _normalize_prompt_text(evidence).casefold()
    return {
        domain for domain in domains
        if any(str(term).casefold() in text for term in ROLE_EVIDENCE_TERMS.get(domain, ()))
    }


def _raw_role_scope(raw: str, tag: str) -> str:
    """Return only the punctuation-delimited user clause attached to one tag."""
    kind_match = re.fullmatch(r"<(Picture|Video|Audio)\s+(\d+)>", str(tag))
    if not kind_match:
        return ""
    kind, index = kind_match.group(1), int(kind_match.group(2))
    aliases = [
        rf"<{kind}\s+{index}>",
        rf"(?:参考图|参考图片|图片|图)\s*{index}" if kind == "Picture" else
        rf"(?:参考视频|视频)\s*{index}" if kind == "Video" else
        rf"(?:参考音频|音频|参考声音|声音)\s*{index}",
    ]
    scopes = []
    for alias in aliases:
        for match in re.finditer(alias, str(raw), flags=re.I):
            start = max(
                str(raw).rfind(mark, 0, match.start()) + 1
                for mark in ("。", ".", "！", "!", "？", "?", "，", ",", "；", ";", "\n")
            )
            ends = [str(raw).find(mark, match.end()) for mark in ("。", ".", "！", "!", "？", "?", "，", ",", "；", ";", "\n")]
            end = min((value for value in ends if value >= 0), default=len(str(raw)))
            scopes.append(str(raw)[start:end])
    return " ".join(scope for scope in scopes if scope).strip()


def _find_task_evidence(raw: str, task_type: str) -> str:
    text = str(raw or "")
    for term in EXPLICIT_TASK_EVIDENCE.get(task_type, ()):
        match = re.search(re.escape(term), text, flags=re.I)
        if match:
            return match.group(0)
    return ""


def _normalize_prompt_text(text) -> str:
    value = "" if text is None else str(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    for _ in range(2):
        value = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    value = value.replace("\u2028", "\n").replace("\u2029", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _clean_generation(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^<\|im_start\|>assistant\s*", "", value, flags=re.I)
    value = re.sub(r"^assistant\s*:?\s*", "", value, flags=re.I)
    value = re.sub(r"^<think>.*?</think>\s*", "", value, flags=re.I | re.S)
    m = re.match(r"^```(?:text|markdown|json)?\s*(.*?)\s*```$", value, flags=re.I | re.S)
    if m:
        value = m.group(1).strip()
    return _normalize_prompt_text(value)


def _extract_json(text: str):
    value = _clean_generation(text)
    try:
        return json.loads(value)
    except Exception:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            return json.loads(value[start:end + 1])
        raise


def _h3_length(seconds: float) -> int:
    return _contract_h3_length(seconds)


def _align_ref_count_down(n: int) -> int:
    n = int(n)
    while n >= 5 and n % 17 != 5:
        n -= 1
    return n


def _q32(v) -> int:
    return max(32, int(round(float(v) / 32.0) * 32))


def _aspect_size_from_tensor(tensor, target_pixels: int):
    h, w = int(tensor.shape[1]), int(tensor.shape[2])
    ratio = float(w) / float(h)
    rw = math.sqrt(max(1, int(target_pixels)) * ratio)
    rh = rw / ratio
    return _q32(rw), _q32(rh)


def _geometry_description(width: int, height: int) -> str:
    ratio = float(width) / float(height)
    orientation = "landscape" if ratio > 1.08 else "portrait" if ratio < 0.92 else "near-square"
    return f"{width}x{height}; aspect={ratio:.4f}; orientation={orientation}"


def _nonnull_dict(values) -> dict:
    if not values:
        return {}
    def sort_key(name):
        text = str(name)
        try:
            return int(text.rsplit("_", 1)[-1]), text
        except (TypeError, ValueError):
            return 10**9, text
    return {
        str(name): values[name]
        for name in sorted(values, key=sort_key)
        if values[name] is not None
    }


def _suffix_index(name: str) -> str:
    return str(name).rsplit("_", 1)[-1]


def _audio_duration(audio) -> float | None:
    return _contract_audio_duration(audio)


def _unload_qwen_clip(qwen_clip) -> str:
    if qwen_clip is None:
        return "not-loaded"
    status = []
    patcher = getattr(qwen_clip, "patcher", None)
    try:
        if patcher is not None and hasattr(comfy.model_management, "unload_model_and_clones"):
            comfy.model_management.unload_model_and_clones(patcher, unload_additional_models=True, all_devices=True)
            status.append("model-unloaded")
        else:
            status.append("no-patcher-or-api")
    except Exception as exc:
        logging.warning("[H3Ref2VAQwen35] Qwen unload failed: %s", exc)
        status.append(f"unload-warning:{type(exc).__name__}")
    try:
        if hasattr(comfy.model_management, "soft_empty_cache"):
            comfy.model_management.soft_empty_cache()
            status.append("soft-empty-cache")
    except Exception as exc:
        status.append(f"soft-cache-warning:{type(exc).__name__}")
    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            status.append("cuda-empty-cache")
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
                status.append("cuda-ipc-collect")
    except Exception as exc:
        status.append(f"cuda-cache-warning:{type(exc).__name__}")
    return ",".join(status)


def _qwen_chat(system: str, user: str, visual_blocks: list[dict]):
    text_blocks, flat_images = [], []
    for block_index, block in enumerate(visual_blocks, start=1):
        tag, kind = block["tag"], block["kind"]
        if kind == "image":
            text_blocks.append(
                f"ISOLATED REFERENCE ASSET {block_index}\nRegistry label: {tag}\nAsset type: Picture\n"
                f"This image belongs ONLY to {tag}.\n<|vision_start|><|image_pad|><|vision_end|>\n"
                f"END ISOLATED REFERENCE ASSET {block_index}"
            )
            flat_images.append(block["images"][0])
        elif kind == "video":
            lines = [
                f"ISOLATED REFERENCE VIDEO {block_index}", f"Registry label: {tag}",
                "Frames are from this asset only, already normalized to 24fps and H3 legal length.",
            ]
            for frame, timestamp in zip(block["images"], block["timestamps"]):
                lines += [f"Timestamp {timestamp:.3f}s", "<|vision_start|><|image_pad|><|vision_end|>"]
                flat_images.append(frame)
            lines.append(f"END ISOLATED REFERENCE VIDEO {block_index}")
            text_blocks.append("\n".join(lines))
    visual_text = ("\n\n".join(text_blocks) + "\n\n") if text_blocks else ""
    chat = (
        f"<|im_start|>system\n{system.strip()}<|im_end|>\n"
        f"<|im_start|>user\n{visual_text}{user.strip()}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    LAST_QWEN_REQUEST_CAPTURE.append({
        "system": system.strip(),
        "user": user.strip(),
        "chat_prompt": chat,
        "media_sequence": [
            {
                "tag": block.get("tag"),
                "kind": block.get("kind"),
                "timestamps": [float(value) for value in block.get("timestamps", [])],
                "image_count": len(block.get("images", [])),
                "image_shapes": [
                    [int(dimension) for dimension in getattr(image, "shape", ())]
                    for image in block.get("images", [])
                ],
            }
            for block in visual_blocks
        ],
        "image_count": len(flat_images),
    })
    return chat, flat_images


def _generate_ref(clip, system: str, user: str, visual_blocks: list[dict], max_tokens: int):
    chat, images = _qwen_chat(system, user, visual_blocks)
    LAST_QWEN_REQUEST_CAPTURE[-1]["generation_options"] = {
        "max_length": max_tokens,
        "do_sample": False,
        "temperature": 0.6,
        "top_k": 64,
        "top_p": 0.95,
        "min_p": 0.05,
        "repetition_penalty": 1.02,
        "presence_penalty": 0.0,
        "seed": 42,
    }
    opts = {"skip_template": True, "min_length": 1, "thinking": False}
    if images:
        opts["images"] = images
    tokens = clip.tokenize(chat, **opts)
    ids = clip.generate(
        tokens, do_sample=False, max_length=max_tokens, temperature=0.6, top_k=64, top_p=0.95,
        min_p=0.05, repetition_penalty=1.02, presence_penalty=0.0, seed=42,
    )
    value = _clean_generation(clip.decode(ids))
    if not value:
        raise RuntimeError("Qwen returned an empty Ref2VA generation result.")
    return value


def _generate_json(clip, system, user, visual_blocks, max_tokens, label):
    first = _generate_ref(clip, system, user, visual_blocks, max_tokens)
    try:
        return _extract_json(first)
    except Exception as e1:
        second = _generate_ref(
            clip, system,
            user + "\n\nReturn ONLY one valid JSON object. No Markdown fence or commentary.",
            visual_blocks, max_tokens,
        )
        try:
            return _extract_json(second)
        except Exception as e2:
            raise RuntimeError(f"{label} failed JSON twice: {type(e1).__name__}; {type(e2).__name__}")


def _sample_normalized_video_for_qwen(video_frames):
    sample_idx = list(range(0, int(video_frames.shape[0]), FPS // 2))
    if len(sample_idx) > MAX_QWEN_VIDEO_FRAMES:
        last = len(sample_idx) - 1
        sample_idx = list(dict.fromkeys(sample_idx[round(i * last / (MAX_QWEN_VIDEO_FRAMES - 1))] for i in range(MAX_QWEN_VIDEO_FRAMES)))
    return [video_frames[i:i+1] for i in sample_idx], [i / FPS for i in sample_idx]


def _canonicalize_user_aliases(raw: str, bundle: dict):
    text = _normalize_prompt_text(raw)
    available = {item["tag"] for item in bundle.get("manifest", [])}
    cn = {1:"一",2:"二",3:"三",4:"四",5:"五",6:"六",7:"七",8:"八",9:"九"}
    generic = [
        (r"(?:参考图片|参考图|图片|图)\s*(\d+)", "Picture"),
        (r"第\s*(\d+)\s*张(?:参考)?(?:图片|图)", "Picture"),
        (r"(?:参考视频|视频)\s*(\d+)", "Video"),
        (r"第\s*(\d+)\s*个(?:参考)?视频", "Video"),
        (r"(?:参考音频|音频|参考声音|声音)\s*(\d+)", "Audio"),
        (r"第\s*(\d+)\s*段(?:参考)?(?:音频|声音)", "Audio"),
        (r"(?<!<)\b(Picture|Video|Audio)\s*(\d+)\b", None),
    ]
    missing = []
    for pattern, fixed_kind in generic:
        for m in re.finditer(pattern, text, flags=re.I):
            if fixed_kind is None:
                kind, idx = m.group(1).title(), int(m.group(2))
            else:
                kind, idx = fixed_kind, int(m.group(1))
            tag = f"<{kind} {idx}>"
            if tag not in available:
                missing.append(tag)
    if missing:
        raise ValueError("User request refers to disconnected assets: " + ", ".join(sorted(set(missing))))
    alias_count = 0
    for idx in range(1, 10):
        specs = [
            (f"<Picture {idx}>", [rf"第\s*{idx}\s*张(?:参考)?(?:图片|图)", rf"第{cn[idx]}张(?:参考)?(?:图片|图)", rf"(?:参考图片|参考图|图片|图)\s*{idx}(?!\d)", rf"(?<!<)\bPicture\s*{idx}\b"]),
            (f"<Video {idx}>", [rf"第\s*{idx}\s*个(?:参考)?视频", rf"第{cn[idx]}个(?:参考)?视频", rf"(?:参考视频|视频)\s*{idx}(?!\d)", rf"(?<!<)\bVideo\s*{idx}\b"]),
            (f"<Audio {idx}>", [rf"第\s*{idx}\s*段(?:参考)?(?:音频|声音)", rf"第{cn[idx]}段(?:参考)?(?:音频|声音)", rf"(?:参考音频|音频|参考声音|声音)\s*{idx}(?!\d)", rf"(?<!<)\bAudio\s*{idx}\b"]),
        ]
        for tag, patterns in specs:
            if tag not in available:
                continue
            for p in patterns:
                text, count = re.subn(p, tag, text, flags=re.I)
                alias_count += count
    return text, alias_count


def _domains_for_kind(kind: str):
    return PICTURE_DOMAINS if kind == "image" else VIDEO_DOMAINS if kind == "video" else AUDIO_DOMAINS


def _role_map_validate(role_map: dict, bundle: dict, raw: str):
    if not isinstance(role_map, dict) or not isinstance(role_map.get("assets"), list):
        raise ValueError("Role Parser must return object with assets list.")
    by_tag = {str(row.get("tag")): row for row in role_map["assets"] if isinstance(row, dict) and row.get("tag")}
    normalized_assets = []
    for item in bundle["manifest"]:
        tag = item["tag"]
        row = by_tag.get(tag)
        if row is None:
            raise ValueError(f"Role Parser omitted {tag}.")
        domains = _domains_for_kind(item["kind"])
        allowed = row.get("allowed", [])
        if not isinstance(allowed, list):
            raise ValueError(f"Invalid ALLOWED for {tag}.")
        allowed = list(dict.fromkeys(str(x) for x in allowed))
        invalid = [x for x in allowed if x not in domains]
        if invalid:
            raise ValueError(f"Invalid role domains for {tag}: {invalid}")
        evidence = _normalize_prompt_text(row.get("evidence", ""))
        if allowed and (not evidence or evidence not in raw):
            raise ValueError(f"Non-empty ALLOWED for {tag} requires exact user-text evidence.")
        evidence_scope = _raw_role_scope(raw, tag) or evidence
        evidence_domains = _evidence_domains(evidence_scope, domains)
        if evidence_domains:
            allowed = [domain for domain in domains if domain in evidence_domains]
        else:
            allowed = []
        allowed = [domain for domain in allowed if domain in evidence_domains]
        normalized_assets.append({
            "tag": tag, "asset_type": item["kind"], "target_entity": row.get("target_entity"),
            "allowed": allowed, "must_not_transfer": [d for d in domains if d not in allowed],
            "role_summary": _normalize_prompt_text(row.get("role_summary", "")), "evidence": evidence,
        })
    # Task authorization is deterministic. The model may propose a task, but
    # only an explicit phrase in the raw request can enable a high-risk task.
    normalized_tasks = [{"type": "reference generation", "evidence": ""}]
    for task_type in sorted(OFFICIAL_TASK_TYPES - {"reference generation"}):
        evidence = _find_task_evidence(raw, task_type)
        if evidence:
            normalized_tasks.append({"type": task_type, "evidence": evidence})
    return {
        "target_entities": role_map.get("target_entities", []) if isinstance(role_map.get("target_entities", []), list) else [],
        "assets": normalized_assets, "task_types": normalized_tasks,
        "target_requirements": role_map.get("target_requirements", []),
        "hard_constraints": role_map.get("hard_constraints", []),
    }


def _role_parser(qwen_clip, raw, canonical, bundle):
    registry_assets = [{
        "tag":i["tag"], "asset_type":i["kind"], "source":i.get("socket"),
        "paired_audio_tag":i.get("paired_audio_tag"), "paired_video_tag":i.get("paired_video_tag"),
    } for i in bundle["manifest"]]
    system = f"""You are the TEXT-ONLY Role Parser for MiniMax H3 Ref2VA.
You do NOT see visual facts. Decide source permissions from user wording only.
A source asset is not a Subject; never assign Subject numbers.
Multiple assets may target the same target_entity.
Unmentioned/ambiguous roles default to allowed=[] rather than broad transfer.
Video presence alone never means editing or continuation. Use video editing only for direct source-video modification; continuation only for explicit extension/resume.
A motion/camera/rhythm reference video is reference generation.

Picture domains: {PICTURE_DOMAINS}
Video domains: {VIDEO_DOMAINS}
Audio domains: {AUDIO_DOMAINS}
Official task types: {sorted(OFFICIAL_TASK_TYPES)}

Every non-empty allowed list needs evidence copied EXACTLY from RAW USER REQUEST. High-risk task types also need exact evidence.
Return ONLY JSON:
{{"target_entities":[{{"id":"T1","description":"..."}}],"assets":[{{"tag":"<Picture 1>","target_entity":"T1","allowed":["identity"],"role_summary":"...","evidence":"exact substring"}}],"task_types":[{{"type":"reference generation","evidence":""}}],"target_requirements":[],"hard_constraints":[]}}"""
    user = f"""RAW USER REQUEST
{raw}

CANONICAL REQUEST
{canonical}

IMMUTABLE REGISTRY
{json.dumps(registry_assets, ensure_ascii=False, indent=2)}

Assign permissions only. Do not describe appearance."""
    first = _generate_json(qwen_clip, system, user, [], 1400, "Role Parser")
    try:
        return _role_map_validate(first, bundle, raw)
    except Exception as exc:
        second = _generate_json(qwen_clip, system, user + f"\n\nContract violation: {exc}\nReturn corrected complete JSON.", [], 1400, "Role Parser repair")
        return _role_map_validate(second, bundle, raw)


def _fact_analyzer_visual(qwen_clip, item, tensor):
    tag, kind = item["tag"], item["kind"]
    domains = _domains_for_kind(kind)
    if kind == "image":
        blocks = [{"tag":tag,"kind":"image","images":[tensor[:1]]}]
    else:
        sampled, timestamps = _sample_normalized_video_for_qwen(tensor)
        blocks = [{"tag":tag,"kind":"video","images":sampled,"timestamps":timestamps}]
    system = f"""You are an ISOLATED visual Fact Analyzer. Analyze exactly ONE asset: {tag}.
Report objective visible facts only. Never decide transfer, role, Subject mapping, or task type.
Use only these domains: {domains}
Return ONLY JSON: {{"tag":"{tag}","asset_type":"{kind}","facts":{{"domain":[]}}}}. Include every domain key; [] if absent."""
    data = _generate_json(qwen_clip, system, f"Analyze only {tag}.", blocks, 900 if kind == "video" else 700, f"Fact Analyzer {tag}")
    facts = data.get("facts", {}) if isinstance(data, dict) else {}
    clean = {}
    for d in domains:
        v = facts.get(d, []) if isinstance(facts, dict) else []
        v = [v] if isinstance(v, str) else v if isinstance(v, list) else []
        clean[d] = [_normalize_prompt_text(x) for x in v if _normalize_prompt_text(x)]
    return {"tag":tag,"asset_type":kind,"facts":clean}


def _fact_analyzer_all(qwen_clip, bundle):
    by_socket = {i["socket"]:i for i in bundle["manifest"]}
    reports = []
    for socket, image in bundle["ref_images"].items():
        reports.append(_fact_analyzer_visual(qwen_clip, by_socket[socket], image))
    for socket, video in bundle["ref_videos"].items():
        reports.append(_fact_analyzer_visual(qwen_clip, by_socket[socket], video))
    for item in bundle["manifest"]:
        if item["kind"] not in {"paired_video_audio","standalone_audio"}:
            continue
        audio = bundle["ref_video_audios"].get(item["socket"]) if item["kind"] == "paired_video_audio" else bundle["ref_audios"].get(item["socket"])
        provenance = f"paired soundtrack of {item.get('paired_video_tag')}" if item["kind"] == "paired_video_audio" else "standalone reference audio"
        reports.append({
            "tag":item["tag"], "asset_type":item["kind"], "facts":{d:[] for d in AUDIO_DOMAINS},
            "provenance":provenance, "technical":{"duration_seconds":_audio_duration(audio),"content_semantics_analyzed":False},
        })
    order = {item["tag"]:i for i,item in enumerate(bundle["manifest"])}
    return sorted(reports, key=lambda x:order.get(x["tag"],999))


def _allowed_fact_pack(role_map, fact_reports):
    roles = {r["tag"]:r for r in role_map["assets"]}
    pack = []
    for report in fact_reports:
        role = roles[report["tag"]]
        allowed = set(role["allowed"])
        selected = {}
        for domain in allowed:
            values = report.get("facts", {}).get(domain, [])
            values = [values] if isinstance(values, str) else values if isinstance(values, list) else []
            clean_values = []
            for value in values:
                value = _normalize_prompt_text(value)
                if not value:
                    continue
                # A fact may be syntactically stored under an allowed domain
                # while semantically describing a denied domain. This is most
                # common for video facts such as "water ripples in background"
                # being emitted under motion.
                if report.get("asset_type") == "video":
                    denied_domains = set(VIDEO_DOMAINS) - allowed
                    cues = [cue for denied in denied_domains for cue in CROSS_DOMAIN_FACT_CUES.get(denied, ())]
                    value_folded = value.casefold()
                    if any(str(cue).casefold() in value_folded for cue in cues):
                        continue
                clean_values.append(value)
            if clean_values:
                selected[domain] = clean_values
        row = {
            "tag":report["tag"], "target_entity":role.get("target_entity"), "allowed_domains":role["allowed"],
            "must_not_transfer":role["must_not_transfer"], "role_summary":role["role_summary"], "allowed_facts_only":selected,
        }
        if report.get("provenance"):
            row["provenance"] = report["provenance"]
        pack.append(row)
    return pack


def _objective_prompt_violations(prompt, bundle, role_map):
    violations = []
    sections = ["subject_definitions:","summary:","retention_analysis:","detailed_description:","overall_soundscape:","non_diegetic_music:"]
    pos = [prompt.find(s) for s in sections]
    if any(p < 0 for p in pos):
        violations.append({"type":"format","detail":"missing required Ref2VA section"})
    elif pos != sorted(pos):
        violations.append({"type":"format","detail":"Ref2VA sections out of order"})
    if "integrated_multimodal_description:" in prompt:
        violations.append({"type":"format","detail":"base-mode field appeared"})
    available = {i["tag"] for i in bundle["manifest"]}
    unknown = sorted(set(re.findall(r"<(?:Picture|Video|Audio)\s+\d+>", prompt)) - available)
    if unknown:
        violations.append({"type":"tag","detail":"unknown tags: " + ", ".join(unknown)})
    if pos[0] >= 0 and pos[1] > pos[0]:
        defs = set(re.findall(r"<Subject\s+\d+>", prompt[pos[0]:pos[1]]))
        used = set(re.findall(r"<Subject\s+\d+>", prompt))
        missing = sorted(used-defs)
        if missing:
            violations.append({"type":"subject","detail":"undefined Subjects: " + ", ".join(missing)})
    allowed_tasks = {x["type"] for x in role_map.get("task_types",[])}
    summary = prompt[pos[1]:pos[2] if pos[2] > pos[1] else len(prompt)].lower() if pos[1] >= 0 else ""
    for task in ["video editing","video continuation","audio reuse","audio reference","keyframe completion"]:
        if task in summary and task not in allowed_tasks:
            violations.append({"type":"task_type","detail":f"unauthorized task type: {task}"})
    if "\\n" in prompt or "\\r" in prompt:
        violations.append({"type":"serialization","detail":"literal newline escape remains"})
    if "<|im_start|>" in prompt or "<|im_end|>" in prompt:
        violations.append({"type":"wrapper","detail":"model wrapper remains"})
    if re.search(r"\b(?:TODO|TBD|PLACEHOLDER|<placeholder>)\b", prompt, flags=re.I):
        violations.append({"type":"placeholder","detail":"placeholder text remains"})
    for match in re.finditer(r"\b(?:task|task_type|task type)\s*[:=]\s*([A-Za-z ]+)", prompt, flags=re.I):
        task = re.sub(r"\s+", " ", match.group(1).strip().lower())
        if task not in OFFICIAL_TASK_TYPES:
            violations.append({"type":"task_type","detail":f"unsupported task type: {task}"})
    return violations


def _sanitize_unauthorized_task_names(prompt: str, role_map: dict) -> str:
    """Prevent a Composer hallucination from re-enabling a task in prose."""
    allowed = {row.get("type") for row in role_map.get("task_types", []) if isinstance(row, dict)}
    value = str(prompt or "")
    for task_type in OFFICIAL_TASK_TYPES - {"reference generation"} - allowed:
        value = re.sub(rf"(?<![A-Za-z]){re.escape(task_type)}(?![A-Za-z])", "reference generation", value, flags=re.I)
    return value


def _semantic_validator(qwen_clip, raw, canonical, role_map, fact_reports, allowed_pack, prompt):
    system = """You are the Semantic Firewall for MiniMax H3 Ref2VA.
Detect unauthorized reference transfer, role confusion, wrong Subject grouping, and wrong task classification.
RAW USER REQUEST is authoritative. ROLE MAP controls source permissions. FULL FACT REPORTS describe each source in isolation. ALLOWED FACT PACK is the only reference-derived fact set Composer may use.
A denied fact is a violation only if imported from that denied source; if raw user independently asks for it, it is allowed.
Assets with the same target_entity should normally feed the same Subject; never require one Subject per Picture.
A motion/camera-only Video must not transfer performer identity, clothing, location, lighting, etc.
An Audio asset with allowed domain full_signal and an explicit audio reuse task authorizes the complete waveform, including its dialogue, lyrics, music, effects, ambience, timbre, and delivery. Do not report those signal components as unauthorized transfers.
Return ONLY JSON: {"pass":true,"violations":[]} or {"pass":false,"violations":[{"type":"unauthorized_transfer","asset":"<Picture 2>","domain":"environment","detail":"..."}]}"""
    user = f"""RAW USER REQUEST
{raw}

CANONICAL REQUEST
{canonical}

ROLE MAP
{json.dumps(role_map, ensure_ascii=False, indent=2)}

FULL FACT REPORTS
{json.dumps(fact_reports, ensure_ascii=False, indent=2)}

ALLOWED FACT PACK
{json.dumps(allowed_pack, ensure_ascii=False, indent=2)}

FINAL PROMPT
{prompt}"""
    data = _generate_json(qwen_clip, system, user, [], 1000, "Semantic Validator")
    violations = data.get("violations", []) if isinstance(data, dict) else [{"type":"validator","detail":"invalid output"}]
    if not isinstance(violations, list):
        violations = [{"type":"validator","detail":"invalid violations field"}]
    violations = [v if isinstance(v,dict) else {"type":"validator","detail":str(v)} for v in violations]
    full_signal_audio_reuse = (
        any(row.get("type") == "audio reuse" for row in role_map.get("task_types", []))
        and any(
            row.get("asset_type") in {"paired_video_audio", "standalone_audio"}
            and "full_signal" in row.get("allowed", [])
            for row in role_map.get("assets", [])
        )
    )
    if full_signal_audio_reuse:
        violations = [
            v for v in violations
            if not (
                str(v.get("type", "")) == "unauthorized_transfer"
                and str(v.get("asset", "")).startswith("<Audio ")
                and str(v.get("domain", "")) in {"audio", *AUDIO_DOMAINS}
            )
        ]
    return {"pass":bool(data.get("pass")) and not violations if isinstance(data,dict) else False, "violations":violations}


def _validator_violations(result):
    if not isinstance(result, dict):
        return [{"type": "validator", "detail": "validator did not return an object"}]
    violations = result.get("violations", [])
    if not isinstance(violations, list):
        violations = [{"type": "validator", "detail": "validator violations field is not a list"}]
    clean = [v if isinstance(v, dict) else {"type": "validator", "detail": str(v)} for v in violations]
    if result.get("pass") is False and not clean:
        clean.append({"type": "validator", "detail": "validator returned pass=false without details"})
    return clean


def _composer(qwen_clip, raw, canonical, bundle, role_map, allowed_pack, official_skill, official_ref, repair_violations=None):
    geometry = _geometry_description(bundle["width"], bundle["height"])
    system = f"""You are the Prompt Composer for MiniMax H3 Ref2VA.
ROLE MAP controls what each source may contribute. ALLOWED FACT PACK is Fact ∩ ALLOWED and is the ONLY reference-derived fact source you may use.
Never reconstruct denied source facts from memory, tag order, or assumptions.
Multiple assets with the same target_entity must be composed into the same reusable Subject where appropriate; never create a Subject merely because a Picture exists.
Use video editing/continuation only if that exact task appears in ROLE MAP.
Preserve all explicit user actions, camera, transitions, dialogue/text/audio/timing/ending requirements.
When ROLE MAP grants an Audio asset full_signal for audio reuse, preserve the complete original waveform as the final audio track; this includes dialogue, lyrics, music, sound effects, ambience, timbre, and delivery.
Calibrate shot density and composition to target duration and geometry. Do not overpack short clips.
Return only the official six-section Ref2VA prompt.

TARGET EFFECTIVE DURATION: {bundle['effective_duration']:.3f}s
TARGET GEOMETRY: {geometry}

===== OFFICIAL SKILL =====
{official_skill}

===== OFFICIAL ref-en.txt =====
{official_ref}"""
    repair = "" if not repair_violations else "\n\nVALIDATOR VIOLATIONS TO REPAIR\n" + json.dumps(repair_violations, ensure_ascii=False, indent=2)
    user = f"""RAW USER REQUEST
{raw}

CANONICAL REQUEST
{canonical}

REFERENCE TAG MAP
{bundle['tag_map']}

ROLE MAP
{json.dumps(role_map, ensure_ascii=False, indent=2)}

ALLOWED FACT PACK
{json.dumps(allowed_pack, ensure_ascii=False, indent=2)}

GENERATION FACTS
Requested duration: {bundle['requested_duration']:.3f}s
Effective duration: {bundle['effective_duration']:.3f}s
Output geometry: {geometry}
Reference image sizing: {bundle['ref_image_size']}
{repair}

Compose the complete official Ref2VA prompt."""
    return _normalize_prompt_text(_generate_ref(qwen_clip, system, user, [], 1900))


class H3Ref2VAReferenceVideoNormalize(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VAReferenceVideoNormalize",
            display_name="H3 Ref2VA Reference Video Normalize — 24fps",
            category="MiniMax H3/Qwen35 Ref2VA",
            description="Resample frames by source time to 24fps, cap to target duration, align down to legal 17k+5 frames, and trim/pad paired audio to the same duration.",
            inputs=[
                io.Image.Input("images"), io.Float.Input("source_fps", force_input=True),
                io.Float.Input("target_duration_seconds", force_input=True), io.Audio.Input("audio", optional=True),
            ],
            outputs=[
                io.Image.Output(display_name="images_24fps"), io.Audio.Output(display_name="audio_synced"),
                io.Float.Output(display_name="fps_24"), io.String.Output(display_name="normalize_report"),
                io.String.Output(display_name="normalize_proof"),
            ],
        )

    @classmethod
    def execute(cls, images, source_fps, target_duration_seconds, audio=None):
        normalized, audio_out, info = _contract_normalize_reference_video(
            images, source_fps, target_duration_seconds, audio
        )
        return io.NodeOutput(
            normalized,
            audio_out,
            REF2VA_FPS,
            info["report"],
            info["proof"],
        )


class H3Ref2VAAssetRegistryQwen35V2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VAAssetRegistryQwen35V2",
            display_name="H3 Ref2VA Asset Registry V2",
            category="MiniMax H3/Qwen35 Ref2VA",
            inputs=[
                io.Int.Input("base_width", force_input=True), io.Int.Input("base_height", force_input=True),
                io.Float.Input("duration_seconds", force_input=True),
                io.Combo.Input("aspect_source", options=["output","auto","picture","video"], default="auto"),
                io.Combo.Input("ref_image_size", options=["match","max"], default="max"),
                io.Autogrow.Input("ref_images", optional=True, template=io.Autogrow.TemplatePrefix(input=io.Image.Input("ref_image"), prefix="ref_image_", min=0, max=9)),
                io.Autogrow.Input("ref_videos", optional=True, template=io.Autogrow.TemplatePrefix(input=io.Image.Input("ref_video"), prefix="ref_video_", min=0, max=3)),
                io.Autogrow.Input("ref_video_fps", optional=True, template=io.Autogrow.TemplatePrefix(input=io.Float.Input("ref_video_fps"), prefix="ref_video_fps_", min=0, max=3)),
                io.Autogrow.Input("ref_video_normalize_proofs", optional=True, template=io.Autogrow.TemplatePrefix(input=io.String.Input("ref_video_normalize_proof"), prefix="ref_video_normalize_proof_", min=0, max=3)),
                io.Autogrow.Input("ref_video_audios", optional=True, template=io.Autogrow.TemplatePrefix(input=io.Audio.Input("ref_video_audio"), prefix="ref_video_audio_", min=0, max=3)),
                io.Autogrow.Input("ref_audios", optional=True, template=io.Autogrow.TemplatePrefix(input=io.Audio.Input("ref_audio"), prefix="ref_audio_", min=0, max=3)),
            ],
            outputs=[io.AnyType.Output(display_name="reference_bundle"),io.String.Output(display_name="reference_tag_map"),io.String.Output(display_name="actual_output_size")],
        )

    @classmethod
    def execute(cls, base_width, base_height, duration_seconds, aspect_source, ref_image_size, ref_images=None, ref_videos=None, ref_video_fps=None, ref_video_normalize_proofs=None, ref_video_audios=None, ref_audios=None):
        duration = float(duration_seconds)
        if duration < 2.0 or duration > 15.0:
            raise ValueError("Ref2VA target duration must be 2-15s.")
        images, videos = _nonnull_dict(ref_images), _nonnull_dict(ref_videos)
        fps_map = _nonnull_dict(ref_video_fps)
        proof_map = _nonnull_dict(ref_video_normalize_proofs)
        paired, standalone = _nonnull_dict(ref_video_audios), _nonnull_dict(ref_audios)
        if not images and not videos and not paired and not standalone:
            raise ValueError("At least one Ref2VA reference asset is required.")
        for video_name, video in videos.items():
            idx = _suffix_index(video_name)
            fps_name = f"ref_video_fps_{idx}"
            if fps_name not in fps_map:
                raise ValueError(f"{video_name} missing {fps_name}; use Reference Video Normalize.")
            if abs(float(fps_map[fps_name]) - 24.0) > 1e-4:
                raise ValueError(f"{video_name} is not normalized to 24fps.")
            n = int(video.shape[0])
            if n < 5 or n % 17 != 5:
                raise ValueError(f"{video_name} has illegal H3 reference length {n}; expected 17k+5.")
            proof_name = f"ref_video_normalize_proof_{idx}"
            if not validate_normalize_proof(proof_map.get(proof_name, ""), n, n / FPS):
                raise ValueError(f"{video_name} is missing a matching Normalize proof; connect the Normalize node directly.")
        for audio_name in paired:
            idx = _suffix_index(audio_name)
            if f"ref_video_{idx}" not in videos:
                raise ValueError(f"{audio_name} requires same-numbered ref_video_{idx}.")
            sync = validate_synced_audio(paired[audio_name], int(videos[f"ref_video_{idx}"].shape[0]) / FPS)
            if not sync["valid"]:
                raise ValueError(f"{audio_name} duration is not synchronized with ref_video_{idx}.")

        width, height, target_pixels, source_used = int(base_width), int(base_height), int(base_width)*int(base_height), "output"
        if aspect_source == "video" and videos:
            width,height = _aspect_size_from_tensor(next(iter(videos.values())), target_pixels); source_used="video"
        elif aspect_source == "picture" and images:
            width,height = _aspect_size_from_tensor(next(iter(images.values())), target_pixels); source_used="picture"
        elif aspect_source == "auto":
            if videos:
                width,height = _aspect_size_from_tensor(next(iter(videos.values())), target_pixels); source_used="video"
            elif images:
                width,height = _aspect_size_from_tensor(next(iter(images.values())), target_pixels); source_used="picture"
        length = _h3_length(duration)
        manifest=[]; p=v=a=0; video_tag_by_socket={}
        for socket in images:
            p+=1; manifest.append({"tag":f"<Picture {p}>","kind":"image","socket":socket})
        for video_name, video in videos.items():
            idx=_suffix_index(video_name); paired_name=f"ref_video_audio_{idx}"
            paired_tag=None
            if paired_name in paired:
                a+=1; paired_tag=f"<Audio {a}>"; manifest.append({"tag":paired_tag,"kind":"paired_video_audio","socket":paired_name,"paired_video_socket":video_name})
            v+=1; video_tag=f"<Video {v}>"; video_tag_by_socket[video_name]=video_tag
            manifest.append({"tag":video_tag,"kind":"video","socket":video_name,"paired_audio_tag":paired_tag,"normalized_fps":24.0,"frame_count":int(video.shape[0]),"duration_seconds":int(video.shape[0])/24.0})
        for item in manifest:
            if item["kind"] == "paired_video_audio":
                item["paired_video_tag"] = video_tag_by_socket.get(item["paired_video_socket"])
        for socket in standalone:
            a+=1; manifest.append({"tag":f"<Audio {a}>","kind":"standalone_audio","socket":socket})
        lines=["REFERENCE TAG MAP — deterministic / immutable","Pictures → per Video [explicit paired Audio then Video] → standalone Audio.","Picture/Video/Audio numbering is independent.","All Videos verified 24fps + legal 17k+5.",""]
        for item in manifest:
            if item["kind"]=="image": lines.append(f'{item["tag"]} ← {item["socket"]} (Picture)')
            elif item["kind"]=="video": lines.append(f'{item["tag"]} ← {item["socket"]} (Video, 24fps, {item["frame_count"]} frames, paired={item.get("paired_audio_tag")})')
            elif item["kind"]=="paired_video_audio": lines.append(f'{item["tag"]} ← {item["socket"]} (paired soundtrack of {item.get("paired_video_tag")})')
            else: lines.append(f'{item["tag"]} ← {item["socket"]} (standalone Audio)')
        tag_map="\n".join(lines)
        actual=f"{width}x{height} | {length} frames | {length/24:.3f}s effective | aspect_source={source_used} | ref_image_size={ref_image_size}"
        bundle={"ref_images":images,"ref_videos":videos,"ref_video_fps":{k:float(v) for k,v in fps_map.items()},"ref_video_normalize_proofs":dict(proof_map),"ref_video_audios":paired,"ref_audios":standalone,"width":width,"height":height,"length":length,"requested_duration":duration,"effective_duration":length/24.0,"aspect_source":str(aspect_source),"aspect_source_used":source_used,"ref_image_size":str(ref_image_size),"manifest":manifest,"tag_map":tag_map,"actual_size":actual}
        return io.NodeOutput(bundle,tag_map,actual)


class H3Ref2VAPromptPipelineQwen35V2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VAPromptPipelineQwen35V2",
            display_name="H3 Ref2VA Prompt Pipeline V2 — Role/Fact/Compose/Validate",
            category="MiniMax H3/Qwen35 Ref2VA",
            inputs=[io.Clip.Input("qwen_clip",lazy=True),io.String.Input("raw_user_request",multiline=True,force_input=True),io.AnyType.Input("reference_bundle"),io.Boolean.Input("enable_standardization",default=True)],
            outputs=[io.String.Output(display_name="final_prompt"),io.String.Output(display_name="standardized_prompt"),io.String.Output(display_name="role_map"),io.String.Output(display_name="fact_reports"),io.String.Output(display_name="validator_report"),io.String.Output(display_name="writer_report")],
        )

    @classmethod
    def check_lazy_status(cls, raw_user_request, reference_bundle, enable_standardization, qwen_clip=None):
        return ["qwen_clip"] if enable_standardization and qwen_clip is None else []

    @staticmethod
    def _skill_files():
        root=Path(__file__).resolve().parent/"skill"; skill=root/"SKILL.md"; guide=root/"references"/"ref-en.txt"
        if not skill.exists() or not guide.exists():
            raise RuntimeError("Official H3 Ref2VA skill files missing; run python download_resources.py in the extracted H3 nodes bundle before copying its node directories.")
        return skill.read_text(encoding="utf-8"),guide.read_text(encoding="utf-8")

    @classmethod
    def execute(cls,raw_user_request,reference_bundle,enable_standardization,qwen_clip=None):
        raw=_normalize_prompt_text(raw_user_request)
        if not raw: raise ValueError("User request is empty.")
        if not enable_standardization:
            msg="Standardization disabled; raw prompt forwarded unchanged."
            return io.NodeOutput(raw,"","","",msg,msg)
        if qwen_clip is None: raise RuntimeError("Qwen3.5 unavailable.")
        official_skill,official_ref=cls._skill_files(); b=reference_bundle
        LAST_QWEN_REQUEST_CAPTURE.clear()
        try:
            canonical,alias_count=_canonicalize_user_aliases(raw,b)
            role_map=_role_parser(qwen_clip,raw,canonical,b)
            fact_reports=_fact_analyzer_all(qwen_clip,b)
            allowed_pack=_allowed_fact_pack(role_map,fact_reports)
            candidate=_sanitize_unauthorized_task_names(_composer(qwen_clip,raw,canonical,b,role_map,allowed_pack,official_skill,official_ref), role_map)
            initial_semantic=_semantic_validator(qwen_clip,raw,canonical,role_map,fact_reports,allowed_pack,candidate)
            first=_objective_prompt_violations(candidate,b,role_map)+_validator_violations(initial_semantic)
            repair_used=bool(first)
            if first:
                candidate=_sanitize_unauthorized_task_names(_composer(qwen_clip,raw,canonical,b,role_map,allowed_pack,official_skill,official_ref,first), role_map)
                final_semantic=_semantic_validator(qwen_clip,raw,canonical,role_map,fact_reports,allowed_pack,candidate)
                final=_objective_prompt_violations(candidate,b,role_map)+_validator_violations(final_semantic)
                validator={"pass":not final,"repair_used":True,"initial_violations":first,"final_violations":final}
                if final:
                    raise ValueError("Ref2VA Semantic Validator failed after one repair. H3 sampling stopped.\n"+json.dumps(validator,ensure_ascii=False,indent=2))
            else:
                validator={"pass":True,"repair_used":False,"initial_violations":[],"final_violations":[]}
            standardized=_normalize_prompt_text(candidate)
            role_text=json.dumps(role_map,ensure_ascii=False,indent=2); fact_text=json.dumps(fact_reports,ensure_ascii=False,indent=2); val_text=json.dumps(validator,ensure_ascii=False,indent=2)
            report=json.dumps({
                "status": "pass",
                "pipeline": "qwen35_reference_standardization",
                "role": "text-only",
                "facts": "isolated-per-asset",
                "composer": "Fact∩ALLOWED",
                "validator": "pass",
                "repair": "used" if repair_used else "not-needed",
                "alias_count": alias_count,
                "request_capture": copy.deepcopy(LAST_QWEN_REQUEST_CAPTURE),
            }, ensure_ascii=False)
        finally:
            unload_status=_unload_qwen_clip(qwen_clip)
        report+=f" Qwen unload: {unload_status}."
        return io.NodeOutput(standardized,standardized,role_text,fact_text,val_text,report)


class H3Ref2VAConditioningFromBundle(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3Ref2VAConditioningFromBundle",display_name="H3 Ref2VA Native Conditioning From Registry",category="MiniMax H3/Qwen35 Ref2VA",inputs=[io.Clip.Input("h3_clip"),io.Vae.Input("vae"),io.Vae.Input("audio_vae"),io.AnyType.Input("reference_bundle"),io.String.Input("final_prompt",multiline=True,force_input=True)],outputs=[io.Conditioning.Output(display_name="positive"),io.Latent.Output(display_name="latent")])
    @classmethod
    def execute(cls,h3_clip,vae,audio_vae,reference_bundle,final_prompt):
        b=reference_bundle
        return MiniMaxH3ReferenceToVideo.execute(h3_clip,vae,audio_vae,_normalize_prompt_text(final_prompt),int(b["width"]),int(b["height"]),int(b["length"]),str(b["ref_image_size"]),b["ref_images"],b["ref_videos"],b["ref_video_audios"],b["ref_audios"])


class H3Ref2VAQwen35PromptPipeline(io.ComfyNode):
    """Fixed Qwen3.5 prompt entry with no standardization toggle."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VAQwen35PromptPipeline",
            display_name="H3 Ref2VA — Qwen3.5 Prompt Standardization",
            category="MiniMax H3/Ref2VA",
            inputs=[
                io.Clip.Input("qwen_clip", lazy=True),
                io.String.Input("raw_user_request", multiline=True, force_input=True),
                io.AnyType.Input("reference_bundle"),
            ],
            outputs=[
                io.String.Output(display_name="final_prompt"),
                io.String.Output(display_name="standardized_prompt"),
                io.String.Output(display_name="role_map"),
                io.String.Output(display_name="fact_reports"),
                io.String.Output(display_name="validator_report"),
                io.String.Output(display_name="writer_report"),
            ],
        )

    @classmethod
    def check_lazy_status(cls, raw_user_request, reference_bundle, qwen_clip=None):
        return ["qwen_clip"] if qwen_clip is None else []

    @classmethod
    def execute(cls, raw_user_request, reference_bundle, qwen_clip=None):
        return H3Ref2VAPromptPipelineQwen35V2.execute(
            raw_user_request, reference_bundle, True, qwen_clip
        )


class H3Ref2VARunMetadataPackV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3Ref2VARunMetadataPackV2",display_name="H3 Ref2VA Run Metadata Pack V2",category="MiniMax H3/Qwen35 Ref2VA",inputs=[io.String.Input("raw_user_request",multiline=True,force_input=True),io.String.Input("standardized_prompt",multiline=True,force_input=True),io.String.Input("final_prompt_used",multiline=True,force_input=True),io.String.Input("reference_tag_map",multiline=True,force_input=True),io.String.Input("role_map",multiline=True,force_input=True),io.String.Input("fact_reports",multiline=True,force_input=True),io.String.Input("validator_report",multiline=True,force_input=True),io.String.Input("actual_output_size",force_input=True),io.String.Input("writer_report",multiline=True,force_input=True),io.AnyType.Input("reference_bundle")],outputs=[io.AnyType.Output(display_name="run_metadata")])
    @classmethod
    def execute(cls,raw_user_request,standardized_prompt,final_prompt_used,reference_tag_map,role_map,fact_reports,validator_report,actual_output_size,writer_report,reference_bundle):
        b=reference_bundle
        payload={"prompt_mode":"qwen35","raw_user_request":_normalize_prompt_text(raw_user_request),"standardized_prompt":_normalize_prompt_text(standardized_prompt),"final_prompt_used":_normalize_prompt_text(final_prompt_used),"standardization_enabled":True,"reference_tag_map":_normalize_prompt_text(reference_tag_map),"role_map":_normalize_prompt_text(role_map),"fact_reports":_normalize_prompt_text(fact_reports),"validator_report":_normalize_prompt_text(validator_report),"actual_output_size":_normalize_prompt_text(actual_output_size),"writer_report":_normalize_prompt_text(writer_report),"mode":"Ref2VA","requested_duration":float(b["requested_duration"]),"effective_duration":float(b["effective_duration"]),"width":int(b["width"]),"height":int(b["height"]),"length":int(b["length"]),"aspect_source":str(b["aspect_source"]),"ref_image_size":str(b["ref_image_size"]),"reference_manifest":copy.deepcopy(b["manifest"]),"reference_video_fps":copy.deepcopy(b.get("ref_video_fps",{})),"reference_video_normalize_proofs":copy.deepcopy(b.get("ref_video_normalize_proofs",{})),"writer_version":WRITER_VERSION}
        return io.NodeOutput(payload)


def _mutate_workflow_for_persistence(workflow,payload):
    if not isinstance(workflow,dict) or not isinstance(workflow.get("nodes"),list): return workflow
    mapping={PERSIST_RAW_REQUEST_NODE_ID:payload.get("raw_user_request",""),PERSIST_STANDARDIZED_PROMPT_NODE_ID:payload.get("standardized_prompt","") or "[standardization disabled]",PERSIST_FINAL_PROMPT_NODE_ID:payload.get("final_prompt_used",""),PERSIST_TAG_MAP_NODE_ID:payload.get("reference_tag_map",""),PERSIST_ROLE_MAP_NODE_ID:payload.get("role_map",""),PERSIST_FACT_REPORTS_NODE_ID:payload.get("fact_reports",""),PERSIST_VALIDATOR_NODE_ID:payload.get("validator_report",""),PERSIST_ACTUAL_SIZE_NODE_ID:payload.get("actual_output_size","")}
    for node in workflow["nodes"]:
        try: nid=int(node.get("id"))
        except Exception: continue
        if nid in mapping: node["widgets_values"]=[_normalize_prompt_text(mapping[nid])]
    return workflow


def _build_persisted_metadata(extra_pnginfo,prompt,payload):
    metadata=copy.deepcopy(extra_pnginfo) if isinstance(extra_pnginfo,dict) else {}
    workflow_blob=metadata.get("workflow")
    if isinstance(workflow_blob,dict): metadata["workflow"]=_mutate_workflow_for_persistence(copy.deepcopy(workflow_blob),payload)
    elif isinstance(workflow_blob,str):
        try:
            parsed=json.loads(workflow_blob)
            if isinstance(parsed,dict): metadata["workflow"]=_mutate_workflow_for_persistence(parsed,payload)
        except Exception: pass
    metadata["h3_ref2va_prompt_writer"]=copy.deepcopy(payload)
    metadata["h3_ref2va_run"]=copy.deepcopy(payload)
    if prompt is not None: metadata["prompt"]=prompt
    return metadata


class H3Ref2VASaveVideoWithMetadataV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3Ref2VASaveVideoWithMetadataV2",display_name="H3 Ref2VA Save Video + Qwen3.5 Metadata",category="MiniMax H3/Ref2VA",is_output_node=True,inputs=[io.Video.Input("video"),io.AnyType.Input("run_metadata"),io.String.Input("filename_prefix",default="videos/H3_Ref2VA_TURBO_v4step600_Qwen35-%year%-%month%-%day%"),io.Combo.Input("format",options=["auto","mp4","mkv","webm"],default="auto"),io.Combo.Input("codec",options=["auto","h264","av1"],default="auto")],hidden=[io.Hidden.prompt,io.Hidden.extra_pnginfo],outputs=[io.Video.Output()])
    @classmethod
    def execute(cls,video,run_metadata,filename_prefix,format,codec):
        payload=copy.deepcopy(run_metadata if isinstance(run_metadata,dict) else {}); payload.setdefault("writer_version",WRITER_VERSION)
        for key in ("raw_user_request","standardized_prompt","final_prompt_used","reference_tag_map","role_map","fact_reports","validator_report","actual_output_size","writer_report"): payload[key]=_normalize_prompt_text(payload.get(key,""))
        format_name=str(format or "auto").casefold(); codec_name=str(codec or "auto").casefold()
        if format_name not in {"auto","mp4","mkv","webm"}: raise ValueError(f"Unsupported video format: {format}")
        if codec_name not in {"auto","h264","av1"}: raise ValueError(f"Unsupported video codec: {codec}")
        if format_name=="webm" and codec_name=="h264": raise ValueError("WebM does not support H.264")
        if format_name=="auto": format_name="webm" if codec_name=="av1" else "mp4"
        width,height=video.get_dimensions(); full,filename,counter,subfolder,_=folder_paths.get_save_image_path(filename_prefix,folder_paths.get_output_directory(),width,height)
        metadata=None if args.disable_metadata else (_build_persisted_metadata(cls.hidden.extra_pnginfo,cls.hidden.prompt,payload) or None)
        file=f"{filename}_{counter:05}_.{Types.VideoContainer.get_extension(format_name)}"
        video.save_to(os.path.join(full,file),format=Types.VideoContainer(format_name),codec=Types.VideoCodec(codec_name),metadata=metadata)
        return io.NodeOutput(video,ui=ui.PreviewVideo([ui.SavedResult(file,subfolder,io.FolderType.output)]))


class H3Ref2VAQwen35Extension(ComfyExtension):
    async def get_node_list(self):
        return [H3Ref2VAReferenceVideoNormalize,H3Ref2VAAssetRegistryQwen35V2,H3Ref2VAPromptPipelineQwen35V2,H3Ref2VAQwen35PromptPipeline,H3Ref2VAConditioningFromBundle,H3Ref2VARunMetadataPackV2,H3Ref2VASaveVideoWithMetadataV2]


async def comfy_entrypoint() -> H3Ref2VAQwen35Extension:
    return H3Ref2VAQwen35Extension()
