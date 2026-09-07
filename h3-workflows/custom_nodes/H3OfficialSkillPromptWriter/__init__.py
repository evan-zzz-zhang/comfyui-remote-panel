from __future__ import annotations

import copy
import json
import math
import os
import re
from pathlib import Path

import folder_paths
import nodes
from comfy_api.latest import io, ui, Types
from comfy.cli_args import args
import comfy.model_management as model_management

NONE = "[None]"

PERSIST_RAW_REQUEST_NODE_ID = 180
PERSIST_STANDARDIZED_PROMPT_NODE_ID = 181
PERSIST_FINAL_PROMPT_NODE_ID = 182


class H3OptionalLoadImageV4:
    CATEGORY = "MiniMax H3/Official Skill Workflow"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    DESCRIPTION = "Optional image uploader. Leave [None] selected when this endpoint is unused."

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        files = [
            f for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f))
        ]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {"required": {"image": ([NONE, *sorted(files)], {"image_upload": True})}}

    def load(self, image):
        if image == NONE:
            return (None,)
        return nodes.LoadImage().load_image(image)[:1]

    @classmethod
    def IS_CHANGED(cls, image):
        if image == NONE:
            return "none"
        return nodes.LoadImage.IS_CHANGED(image)

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        if image == NONE:
            return True
        return nodes.LoadImage.VALIDATE_INPUTS(image)


class H3InputResolverV4:
    CATEGORY = "MiniMax H3/Official Skill Workflow"
    FUNCTION = "resolve"
    RETURN_TYPES = ("IMAGE", "IMAGE", "INT", "INT", "INT", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = (
        "first_frame", "last_frame", "width", "height",
        "h3_length", "effective_duration", "mode", "resolver_report"
    )
    DESCRIPTION = (
        "Deterministically resolves T2VA/I2VA/L2VA/FL2VA, "
        "H3 frame count, and output size. It never rewrites the user prompt."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_width": ("INT", {"forceInput": True}),
                "base_height": ("INT", {"forceInput": True}),
                "duration_seconds": ("FLOAT", {"forceInput": True}),
                "use_reference_aspect": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
            },
        }

    @staticmethod
    def _q(v, multiple=32):
        return max(multiple, int(round(float(v) / multiple) * multiple))

    @staticmethod
    def _h3_length(seconds):
        n = max(5, round(float(seconds) * 24))
        return int(n + (5 - (n % 17)) % 17)

    def _aspect_size(self, image, target_pixels):
        h, w = int(image.shape[1]), int(image.shape[2])
        ratio = w / h
        rw = math.sqrt(max(1, target_pixels) * ratio)
        rh = rw / ratio
        return self._q(rw), self._q(rh)

    def resolve(
        self,
        base_width,
        base_height,
        duration_seconds,
        use_reference_aspect,
        first_frame=None,
        last_frame=None,
    ):
        requested = float(duration_seconds)
        if requested < 4.0 or requested > 15.0:
            raise ValueError("MiniMax H3 duration must be between 4 and 15 seconds.")

        has_first = first_frame is not None
        has_last = last_frame is not None
        mode = (
            "FL2VA" if has_first and has_last
            else "I2VA" if has_first
            else "L2VA" if has_last
            else "T2VA"
        )

        width, height = int(base_width), int(base_height)
        notes = []
        if use_reference_aspect and (has_first or has_last):
            anchor = first_frame if has_first else last_frame
            width, height = self._aspect_size(anchor, int(base_width) * int(base_height))
            notes.append(
                "reference aspect enabled; first frame has priority when both endpoints exist"
            )
            if has_first and has_last:
                r1 = float(first_frame.shape[2]) / float(first_frame.shape[1])
                r2 = float(last_frame.shape[2]) / float(last_frame.shape[1])
                if abs(math.log(r1 / r2)) > 0.08:
                    notes.append(
                        "first/last frame aspect ratios differ noticeably; canvas follows first frame"
                    )
        else:
            notes.append("manual aspect/MP canvas used")

        length = self._h3_length(requested)
        effective = length / 24.0
        report = (
            f"Mode: {mode}. Requested duration: {requested:.3f}s. "
            f"Effective H3 duration: {effective:.3f}s ({length} frames). "
            f"Canvas: {width}x{height}. " + "; ".join(notes)
        )
        return first_frame, last_frame, width, height, length, effective, mode, report


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


def _qwen_chat(system: str, user: str, visual_bindings: list[str]) -> str:
    blocks = []
    for index, binding in enumerate(visual_bindings, start=1):
        blocks.append(
            f"REFERENCE ASSET BLOCK {index}\n"
            f"{binding.strip()}\n"
            "<|vision_start|><|image_pad|><|vision_end|>\n"
            f"END REFERENCE ASSET BLOCK {index}"
        )
    visual = ("\n\n".join(blocks) + "\n\n") if blocks else ""
    return (
        f"<|im_start|>system\n{system.strip()}<|im_end|>\n"
        f"<|im_start|>user\n{visual}{user.strip()}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def _generate(clip, system: str, user: str, images: list, visual_bindings: list[str], max_tokens: int) -> str:
    if len(images) != len(visual_bindings):
        raise ValueError(
            f"Visual binding mismatch: {len(images)} image(s) but "
            f"{len(visual_bindings)} binding label(s)."
        )

    chat = _qwen_chat(system, user, visual_bindings)
    opts = {"skip_template": True, "min_length": 1, "thinking": False}
    if images:
        opts["images"] = images

    tokens = clip.tokenize(chat, **opts)
    ids = clip.generate(
        tokens,
        do_sample=False,
        max_length=max_tokens,
        temperature=0.6,
        top_k=64,
        top_p=0.95,
        min_p=0.05,
        repetition_penalty=1.02,
        presence_penalty=0.0,
        seed=42,
    )
    value = _clean_generation(clip.decode(ids))
    if not value:
        raise RuntimeError("Qwen returned an empty prompt-generation result.")
    return value


def _quoted_literals(text: str) -> list[str]:
    found = []
    patterns = [r'“([^”]+)”', r'「([^」]+)」', r'『([^』]+)』', r'"([^"\n]+)"']
    for pat in patterns:
        found.extend(m.group(1) for m in re.finditer(pat, text))
    return list(dict.fromkeys(x for x in found if x.strip()))


def _structure_warnings(prompt: str, mode: str, raw_request: str) -> list[str]:
    warnings = []
    names = [
        "integrated_multimodal_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ]
    positions = [prompt.find(x) for x in names]
    if any(p < 0 for p in positions):
        warnings.append("missing one or more required H3 base sections")
    elif positions != sorted(positions):
        warnings.append("H3 base sections are out of order")

    if "[Shot 1]" not in prompt:
        warnings.append("missing [Shot 1]")

    leading = prompt.lstrip()
    if (
        mode == "I2VA"
        and not leading.startswith("For the target video, at 0.00 seconds into the target video")
    ):
        warnings.append("missing official I2VA first-frame alignment instruction")
    if (
        mode in {"FL2VA", "L2VA"}
        and not leading.startswith("How the reference pictures align with the target video")
    ):
        warnings.append(f"missing official {mode} endpoint alignment instruction")
    if mode == "FL2VA" and not ("Picture 1" in prompt and "Picture 2" in prompt):
        warnings.append("FL2VA output does not reference both Picture 1 and Picture 2")
    if mode in {"I2VA", "L2VA"} and "Picture 1" not in prompt:
        warnings.append(f"{mode} output does not reference Picture 1")

    for literal in _quoted_literals(raw_request):
        if literal not in prompt:
            warnings.append(f"quoted user text was not preserved verbatim: {literal}")

    if "\\n" in prompt or "\\r" in prompt:
        warnings.append("final prompt still contains literal escape sequences")
    return warnings


def _unload_prompt_clip_vram(clip) -> str:
    """Fully unload only the Qwen prompt-writer CLIP patcher from VRAM.

    The CLIP Python object remains alive/cached and can be loaded again on the next queue.
    Other ComfyUI models are intentionally left alone.
    """
    patcher = getattr(clip, "patcher", None)
    if patcher is None:
        return "Qwen VRAM release: skipped (no clip.patcher)."

    try:
        device = patcher.load_device
    except Exception:
        device = None

    before = None
    after = None
    try:
        if device is not None:
            before = model_management.get_free_memory(device)
    except Exception:
        pass

    matched = []
    try:
        # Strong object references avoid index-shift/finalizer races while unloading.
        for loaded_model in list(model_management.current_loaded_models):
            try:
                if loaded_model.model is patcher:
                    matched.append(loaded_model)
            except Exception:
                continue
    except Exception as e:
        return f"Qwen VRAM release: lookup failed ({type(e).__name__}: {e})."

    if not matched:
        # It may already have been offloaded by ComfyUI during generation.
        try:
            model_management.soft_empty_cache()
        except Exception:
            pass
        return "Qwen VRAM release: already absent from ComfyUI loaded-model list."

    unloaded = 0
    warnings = []
    for loaded_model in matched:
        try:
            loaded_model.currently_used = False
            loaded_model.model_unload()
            unloaded += 1
        except Exception as e:
            warnings.append(f"{type(e).__name__}: {e}")
        finally:
            try:
                if loaded_model in model_management.current_loaded_models:
                    model_management.current_loaded_models.remove(loaded_model)
            except Exception:
                pass

    try:
        model_management.soft_empty_cache()
    except Exception as e:
        warnings.append(f"soft_empty_cache: {type(e).__name__}: {e}")

    try:
        if device is not None:
            after = model_management.get_free_memory(device)
    except Exception:
        pass

    parts = [f"Qwen VRAM release: unloaded {unloaded} matching model(s)."]
    if before is not None and after is not None:
        delta = max(0, after - before) / (1024 ** 3)
        parts.append(f"reported free-VRAM increase ≈ {delta:.2f} GiB.")
    if warnings:
        parts.append("warnings: " + " | ".join(warnings))
    return " ".join(parts)


class H3OfficialSkillPromptWriterQwen:
    CATEGORY = "MiniMax H3/Official Skill Workflow"
    FUNCTION = "write"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "final_prompt", "requirements_lock", "writer_report", "standardized_prompt"
    )
    DESCRIPTION = (
        "Natural-language + endpoint images -> Qwen3.5 -> official MiniMax H3 base prompt. "
        "v4.4 actively unloads the prompt-writer Qwen model from VRAM after prompt generation."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP", {"lazy": True}),
                "raw_user_request": (
                    "STRING",
                    {"forceInput": True, "multiline": True, "dynamicPrompts": False},
                ),
                "mode": ("STRING", {"forceInput": True}),
                "requested_duration": ("FLOAT", {"forceInput": True}),
                "effective_duration": ("FLOAT", {"forceInput": True}),
                "h3_length": ("INT", {"forceInput": True}),
                "width": ("INT", {"forceInput": True}),
                "height": ("INT", {"forceInput": True}),
                "enable_standardization": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
            },
        }

    def check_lazy_status(
        self,
        raw_user_request,
        mode,
        requested_duration,
        effective_duration,
        h3_length,
        width,
        height,
        enable_standardization,
        clip=None,
        first_frame=None,
        last_frame=None,
    ):
        if enable_standardization and clip is None:
            return ["clip"]
        return []

    @staticmethod
    def _skill_files():
        root = Path(__file__).resolve().parent / "skill"
        skill = root / "SKILL.md"
        guide = root / "references" / "base-en.txt"
        if not skill.exists() or not guide.exists():
            raise RuntimeError(
                "Official MiniMax H3 skill files are missing. "
                "Run python download_resources.py in the extracted H3 nodes bundle before copying its node directories."
            )
        return skill.read_text(encoding="utf-8"), guide.read_text(encoding="utf-8")

    def write(
        self,
        raw_user_request,
        mode,
        requested_duration,
        effective_duration,
        h3_length,
        width,
        height,
        enable_standardization,
        clip=None,
        first_frame=None,
        last_frame=None,
    ):
        raw = _normalize_prompt_text(raw_user_request)
        if not raw:
            raise ValueError("User natural-language request is empty.")

        if not enable_standardization:
            return (
                raw,
                "",
                "Prompt standardization disabled: raw request forwarded unchanged; Qwen was not loaded.",
                "",
            )

        if clip is None:
            raise RuntimeError("Prompt standardization is enabled but Qwen CLIP is unavailable.")
        for method in ("tokenize", "generate", "decode"):
            if not callable(getattr(clip, method, None)):
                raise RuntimeError(
                    f"Connected prompt model is not generation-capable: missing clip.{method}()."
                )

        official_skill, official_base = self._skill_files()

        images = []
        visual_bindings = []
        if first_frame is not None:
            images.append(first_frame[:1])
            visual_bindings.append(
                f"<Picture 1> — EXACT FIRST FRAME at 0.00 seconds. "
                f"This image is the opening endpoint for mode {mode}. "
                "All opening-state visual facts must come from THIS image only."
            )
        if last_frame is not None:
            images.append(last_frame[:1])
            picture_number = 2 if first_frame is not None else 1
            visual_bindings.append(
                f"<Picture {picture_number}> — EXACT LAST FRAME at "
                f"{float(effective_duration):.2f} seconds. "
                f"This image is the ending endpoint for mode {mode}. "
                "All ending-state visual facts must come from THIS image only."
            )

        if visual_bindings:
            visual_context = (
                "Reference assets are attached in separately labeled visual blocks. "
                "Each label applies ONLY to the image immediately following that label. "
                "Never swap or merge image roles."
            )
        else:
            visual_context = "No reference images are supplied."

        endpoints_pixel_identical = False
        if first_frame is not None and last_frame is not None:
            try:
                a = first_frame[:1]
                b = last_frame[:1]
                endpoints_pixel_identical = bool(
                    tuple(a.shape) == tuple(b.shape) and (a == b).all().item()
                )
            except Exception:
                endpoints_pixel_identical = False

        offload_report = "Qwen VRAM release: not attempted."
        try:
            req_system = """You are a strict multimodal requirement-and-reference fact interpreter for MiniMax H3.
The user's text may be casual natural language, production instructions, a partial prompt, or a complete prompt.

Do NOT write an H3 prompt yet.
Do NOT invent story facts.
Do NOT reinterpret an endpoint image to make it fit an intermediate requested action.

Return exactly these sections in English, in this order:

USER_REQUIREMENTS:
- Preserve every explicit requested subject, action, state change, dialogue/lyrics/visible text, timing, ending condition, and constraint.

CAMERA_AND_TRANSITIONS:
- Preserve every explicit camera move, framing change, transition mechanism, cut, zoom/push/pull, and requested spatial path.

AUDIO_AND_MUSIC_REQUESTS:
- List only audio/music requirements explicitly requested by the user. If none were requested, write N/A.

PICTURE_1_FACTS:
- If Picture 1 exists, record only directly visible objective facts: visual style, subject appearance, pose/facing direction, framing/composition, environment/background, lighting/colors, and salient objects.
- Never infer an unseen front/back view, emotion, action, or future state.
- If Picture 1 does not exist, write N/A.

PICTURE_2_FACTS:
- If Picture 2 exists, record only directly visible objective facts using the same categories.
- Never copy Picture 1 facts into Picture 2 unless the actual attached image supports them.
- Never rewrite Picture 2 to match the user's desired intermediate action.
- If Picture 2 does not exist, write N/A.

ENDPOINT_RELATIONSHIP:
- State the actual endpoint roles and deterministic relationship supplied by the application.
- If endpoint images are pixel-identical, treat that as a hard fact: motion may leave the start state, but the final state must converge back to the exact visible endpoint.
- Do not infer that identical endpoints necessarily mean a seamless loop unless the user asks for looping.

Quoted dialogue, lyrics, and visible text must remain verbatim in their original language."""

            req_user = f"""RAW USER REQUEST — HIGHEST AUTHORITY
{raw}

GENERATION FACTS
Mode: {mode}
Requested duration: {float(requested_duration):.3f}s
Effective H3 duration: {float(effective_duration):.3f}s ({int(h3_length)} frames at 24 FPS)
Canvas: {int(width)}x{int(height)}
Endpoint images pixel-identical: {"YES" if endpoints_pixel_identical else "NO/NOT DETERMINED"}
{visual_context}

Build the structured requirement-and-reference FACT LOCK. Do not convert it into an H3 prompt yet."""

            requirement_lock = _generate(
                clip, req_system, req_user, images, visual_bindings, 800
            )
            requirement_lock = _normalize_prompt_text(requirement_lock)

            app_contract = """APPLICATION CONTRACT — applies while executing the official skill:
1. RAW USER REQUEST is the highest creative authority. It may be a request/instruction rather than a prompt.
2. Do not omit, weaken, substitute, or contradict explicit requested actions, camera movements, transitions, dialogue/lyrics/visible text, audio requests, timing, ending state, or constraints.
3. REQUIREMENT / FACT LOCK is authoritative for extracted endpoint visual facts and explicit user requirements. If its user-requirement wording conflicts with RAW USER REQUEST, RAW USER REQUEST wins; objective PICTURE_1_FACTS and PICTURE_2_FACTS must not be contradicted.
4. Each labeled REFERENCE ASSET BLOCK is authoritative only for the image immediately following its label. Never swap Picture 1/Picture 2 or merge their endpoint roles.
5. An intermediate action does NOT redefine the final reference image. If the requested middle action differs from Picture 2, describe the action in the middle and then explicitly converge back to Picture 2 at the end.
6. You may add useful production detail when consistent with the request and actual reference images.
7. If the user already supplied prompt-like wording, preserve its content and make only changes required by the official H3 structure.
8. Before answering, internally check every item in the REQUIREMENT / FACT LOCK against the final prompt, especially Picture 1 and Picture 2 endpoint facts.
9. Return only the final H3 prompt, with no Markdown fence, preface, explanation, or analysis."""

            writer_system = (
                app_contract
                + "\n\n===== OFFICIAL MiniMax H3 SKILL =====\n"
                + official_skill
                + "\n\n===== OFFICIAL base-en.txt =====\n"
                + official_base
            )

            writer_user = f"""RAW USER REQUEST — HIGHEST AUTHORITY
{raw}

REQUIREMENT / REFERENCE FACT LOCK — user requirements and endpoint visual facts must survive
{requirement_lock}

GENERATION FACTS
Mode: {mode}
Requested duration: {float(requested_duration):.3f}s
Effective H3 duration: {float(effective_duration):.3f}s ({int(h3_length)} frames at 24 FPS)
Canvas: {int(width)}x{int(height)}
{visual_context}

Execute the official h3-prompt-writing skill. Use the actual attached images when present. Produce the final MiniMax H3 prompt only."""

            candidate = _generate(
                clip, writer_system, writer_user, images, visual_bindings, 1200
            )
            candidate = _normalize_prompt_text(candidate)
            warnings = _structure_warnings(candidate, str(mode), raw)

            if warnings:
                repair_system = (
                    writer_system
                    + "\n\nREPAIR RULE: Correct the candidate while preserving RAW USER REQUEST "
                    "and REQUIREMENT / FACT LOCK. Return only the complete repaired H3 prompt."
                )
                repair_user = (
                    f"""RAW USER REQUEST
{raw}

REQUIREMENT / FACT LOCK
{requirement_lock}

VALIDATION PROBLEMS
- """
                    + "\n- ".join(warnings)
                    + f"""

CANDIDATE H3 PROMPT
{candidate}

Repair it now. Do not delete any user requirement or endpoint fact."""
                )
                repaired = _generate(
                    clip, repair_system, repair_user, images, visual_bindings, 1200
                )
                repaired = _normalize_prompt_text(repaired)
                repaired_warnings = _structure_warnings(repaired, str(mode), raw)
                if not repaired_warnings:
                    candidate = repaired
                    warnings = []
                else:
                    warnings = repaired_warnings

            standardized = _normalize_prompt_text(candidate)

        finally:
            # v4.4 key change: Qwen is never needed after this node finishes.
            # Fully remove only this CLIP patcher from ComfyUI's loaded-model list,
            # then release allocator cache before H3 32B conditioning/UNET begins.
            offload_report = _unload_prompt_clip_vram(clip)

        report = (
            f"Official-skill standardization completed. Mode={mode}; "
            f"images analyzed={len(images)}; visual-binding=label-adjacent; "
            f"reference-fact-lock=v4.3; newline-normalization=v4.2; "
            f"prompt-qwen-active-unload=v4.4. {offload_report}"
        )
        if warnings:
            report += " Remaining validation warnings: " + "; ".join(warnings)

        return standardized, requirement_lock, report, standardized


class H3RunMetadataPack:
    CATEGORY = "MiniMax H3/Official Skill Workflow"
    FUNCTION = "pack"
    RETURN_TYPES = ("H3_RUN_METADATA",)
    RETURN_NAMES = ("run_metadata",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "raw_user_request": ("STRING", {"forceInput": True, "multiline": True}),
                "standardized_prompt": ("STRING", {"forceInput": True, "multiline": True}),
                "final_prompt_used": ("STRING", {"forceInput": True, "multiline": True}),
                "mode": ("STRING", {"forceInput": True}),
                "requested_duration": ("FLOAT", {"forceInput": True}),
                "effective_duration": ("FLOAT", {"forceInput": True}),
                "width": ("INT", {"forceInput": True}),
                "height": ("INT", {"forceInput": True}),
                "writer_report": ("STRING", {"forceInput": True, "multiline": True}),
            }
        }

    def pack(
        self,
        raw_user_request,
        standardized_prompt,
        final_prompt_used,
        mode,
        requested_duration,
        effective_duration,
        width,
        height,
        writer_report,
    ):
        raw = _normalize_prompt_text(raw_user_request)
        standardized = _normalize_prompt_text(standardized_prompt)
        final = _normalize_prompt_text(final_prompt_used)
        payload = {
            "raw_user_request": raw,
            "standardized_prompt": standardized,
            "final_prompt_used": final,
            "standardization_enabled": bool(standardized.strip()),
            "mode": str(mode),
            "requested_duration": float(requested_duration),
            "effective_duration": float(effective_duration),
            "width": int(width),
            "height": int(height),
            "writer_report": _normalize_prompt_text(writer_report),
            "writer_version": "v4.4",
        }
        return (payload,)


def _mutate_workflow_for_persistence(workflow, payload):
    if not isinstance(workflow, dict):
        return workflow
    nodes_blob = workflow.get("nodes")
    if not isinstance(nodes_blob, list):
        return workflow

    mapping = {
        PERSIST_RAW_REQUEST_NODE_ID: payload.get("raw_user_request", ""),
        PERSIST_STANDARDIZED_PROMPT_NODE_ID: (
            payload.get("standardized_prompt", "")
            or "[This run had prompt standardization disabled.]"
        ),
        PERSIST_FINAL_PROMPT_NODE_ID: payload.get("final_prompt_used", ""),
    }
    for node in nodes_blob:
        try:
            node_id = int(node.get("id"))
        except Exception:
            continue
        if node_id in mapping:
            node["widgets_values"] = [_normalize_prompt_text(mapping[node_id])]
    return workflow


def _build_persisted_metadata(extra_pnginfo, prompt, payload):
    metadata = copy.deepcopy(extra_pnginfo) if isinstance(extra_pnginfo, dict) else {}

    workflow_blob = metadata.get("workflow")
    if isinstance(workflow_blob, dict):
        metadata["workflow"] = _mutate_workflow_for_persistence(
            copy.deepcopy(workflow_blob), payload
        )
    elif isinstance(workflow_blob, str):
        try:
            parsed = json.loads(workflow_blob)
            if isinstance(parsed, dict):
                metadata["workflow"] = _mutate_workflow_for_persistence(parsed, payload)
        except Exception:
            pass

    metadata["h3_prompt_writer"] = copy.deepcopy(payload)
    if prompt is not None:
        metadata["prompt"] = prompt
    return metadata


class H3SaveVideoWithPromptMetadata:
    CATEGORY = "MiniMax H3/Official Skill Workflow"
    FUNCTION = "save_video_with_metadata"
    OUTPUT_NODE = True
    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "run_metadata": ("H3_RUN_METADATA",),
                "filename_prefix": (
                    "STRING",
                    {"default": "videos/H3_Qwen35-%year%-%month%-%day%"},
                ),
                "format": (["auto", "mp4", "mkv", "webm"], {"default": "auto"}),
                "codec": (["auto", "h264", "av1"], {"default": "auto"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    def save_video_with_metadata(
        self,
        video,
        run_metadata,
        filename_prefix,
        format,
        codec,
        prompt=None,
        extra_pnginfo=None,
    ):
        payload = copy.deepcopy(run_metadata if isinstance(run_metadata, dict) else {})
        payload.setdefault("raw_user_request", "")
        payload.setdefault("standardized_prompt", "")
        payload.setdefault(
            "final_prompt_used",
            payload.get("standardized_prompt") or payload.get("raw_user_request", ""),
        )
        payload.setdefault(
            "standardization_enabled",
            bool(_normalize_prompt_text(payload.get("standardized_prompt", ""))),
        )
        payload.setdefault("writer_version", "v4.4")

        for key in (
            "raw_user_request",
            "standardized_prompt",
            "final_prompt_used",
            "writer_report",
        ):
            payload[key] = _normalize_prompt_text(payload.get(key, ""))

        format_name = str(format or "auto").casefold()
        codec_name = str(codec or "auto").casefold()

        if format_name not in {"auto", "mp4", "mkv", "webm"}:
            raise ValueError(f"Unsupported video format: {format}")
        if codec_name not in {"auto", "h264", "av1"}:
            raise ValueError(f"Unsupported video codec: {codec}")
        if format_name == "webm" and codec_name == "h264":
            raise ValueError("WebM does not support H.264 in this saver.")
        if format_name == "auto":
            format_name = "webm" if codec_name == "av1" else "mp4"

        width, height = video.get_dimensions()
        (
            full_output_folder,
            filename,
            counter,
            subfolder,
            filename_prefix,
        ) = folder_paths.get_save_image_path(
            filename_prefix,
            folder_paths.get_output_directory(),
            width,
            height,
        )

        saved_metadata = None
        if not args.disable_metadata:
            saved_metadata = _build_persisted_metadata(
                extra_pnginfo=extra_pnginfo,
                prompt=prompt,
                payload=payload,
            )
            if not saved_metadata:
                saved_metadata = None

        file = (
            f"{filename}_{counter:05}_."
            f"{Types.VideoContainer.get_extension(format_name)}"
        )
        video.save_to(
            os.path.join(full_output_folder, file),
            format=Types.VideoContainer(format_name),
            codec=Types.VideoCodec(codec_name),
            metadata=saved_metadata,
        )

        return io.NodeOutput(
            video,
            ui=ui.PreviewVideo(
                [ui.SavedResult(file, subfolder, io.FolderType.output)]
            ),
        )


NODE_CLASS_MAPPINGS = {
    "H3OptionalLoadImageV4": H3OptionalLoadImageV4,
    "H3InputResolverV4": H3InputResolverV4,
    "H3OfficialSkillPromptWriterQwen": H3OfficialSkillPromptWriterQwen,
    "H3RunMetadataPack": H3RunMetadataPack,
    "H3SaveVideoWithPromptMetadata": H3SaveVideoWithPromptMetadata,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3OptionalLoadImageV4": "H3 Optional Load Image V4",
    "H3InputResolverV4": "H3 Input Resolver V4",
    "H3OfficialSkillPromptWriterQwen": "H3 Official Skill Prompt Writer — Qwen",
    "H3RunMetadataPack": "H3 Run Metadata Pack",
    "H3SaveVideoWithPromptMetadata": "H3 Save Video With Prompt Metadata",
}
