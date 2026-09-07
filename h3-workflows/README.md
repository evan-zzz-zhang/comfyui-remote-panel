# H3 companion workflows for Comfy Remote v0.4.8

[简体中文](README.zh-CN.md)

This optional collection contains 18 workflows: **FL2VA / Ref2VA × original / LightX2V / v4step600 × Raw / Ollama / Qwen3.5**. H3 is not required for generic ComfyUI API workflows in Comfy Remote.

## Choose a package

| Release asset | Contents | Use |
| --- | --- | --- |
| `comfy-remote-h3-panel-0.4.8.zip` | 18 canonical API graphs and manifests | Comfy Remote's specialized creation flow |
| `comfy-remote-h3-comfyui-0.4.8.zip` | 18 native visual workflow JSON files | Open directly in the ComfyUI canvas |
| `comfy-remote-h3-nodes-0.4.8.zip` | Three required custom-node packages and a guide downloader | Install into ComfyUI for either workflow package |

The Release also supplies SHA256 checksums. Model weights, LoRAs, reference media, generated outputs and official prompt guides are not included.

## Install dependencies

1. Use ComfyUI **0.26.0 or newer**, with the native MiniMax H3, Qwen3.5 CLIP, audio/video and dynamic-input node support. A version number alone does not guarantee that every model/node is available; check missing-node messages before running.
2. Install [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) for `LazySwitchKJ` in the FL2VA Ollama workflows.
3. Extract the nodes ZIP to a staging directory. Read [third-party notices](THIRD_PARTY_NOTICES.md), then run `python download_resources.py` from that directory. This fetches only pinned official prompt text, verifies SHA256, and refuses to replace modified existing files. It neither downloads models nor executes downloaded text. Internet access is needed for this step. For offline machines, complete it on another machine and transfer the prepared node directories.
4. Copy the three directories **inside** `custom_nodes` into your ComfyUI `custom_nodes` directory: `ComfyRemoteH3PromptWriter`, `H3OfficialSkillPromptWriter`, and `H3Ref2VAQwen35`. Restart ComfyUI when no generation is active. These use ComfyUI's existing Python dependencies (`torch`, `numpy`, `Pillow`, `av`); do not install packages into an unrelated system Python.
5. If an older locally patched node pack already registers the same H3 class names, back it up and disable the duplicate before installing. The public Prompt Writer web extension can be retained only if it does not register these same node classes. The included Prompt Writer package exposes workflow nodes only, with no extra HTTP routes or web UI. No ComfyUI core files need to be patched.
6. Install the H3 video/audio VAEs, H3 generation model, H3 text encoder and, for accelerated modes, the matching LoRA. The exact filenames and model links are in each canonical manifest's dependency metadata. Qwen3.5 workflows additionally require `qwen3.5_4b_bf16.safetensors`. Ollama workflows require a reachable local Ollama service and the selected model (default `gemma4:e4b`). Model licenses apply separately.

## Use with Comfy Remote

Comfy Remote v0.4.8 already includes the canonical 18 API graphs/manifests. After installing ComfyUI dependencies, use the existing FL2VA/Ref2VA selectors. The panel ZIP is a separate copy for inspection, deployment and reuse; reinstalling it is normally unnecessary.

For a custom asset deployment, copy the ZIP's `workflows` contents into the directory configured by `[storage].workflow_dir`, preserving `family/mode/backend/manifest.json` and `workflow.json`. Custom presets with the same ID override bundled presets, so back up existing custom assets first. Do not import the visual JSON as a replacement for the specialized manifests. Generic API import remains available separately.

## Use directly in ComfyUI

Open or drag one JSON from `comfyui/` into the canvas. Select your installed models and upload/select your own files in the image/video loader nodes. `reference-image.png` and `reference-video.mp4` are deliberately nonexistent placeholders. Relative model subfolders may need reselection on a different OS. Examples use INT8 H3 model paths and fixed seeds; they are not an automatic BF16 switch.

FL2VA examples start with a first-frame input. Add a last-frame image to the existing optional reference input when needed. Ref2VA examples include one image and one video; unused optional collection inputs remain available for expansion. Keep the audio/video pairing and normalization connections intact when adding references. Change the plain-language request in the prompt node. In Ref2VA Qwen examples the separate canonical role request is a snapshot prepared by the panel: when changing roles, edit that request too, or regenerate through the panel. The standalone canvas does not run the panel's preprocessing.

## Validation and limits

All 18 visual graphs were imported/exported through ComfyUI and checked against synthetic API examples built by the panel, including dynamic inputs, links and widget values. Writer seeds are fixed in examples for reproducibility. Existing device acceptance covers FL2VA 9/9 and Ref2VA 9/9 INT8 generation, Qwen Ref2VA role replacement, a simple Ollama character case and representative BF16 generation. Raw language understanding and complex character recognition remain model limitations. This is not an all-model/all-hardware guarantee; new clean-install GPU acceptance and a full BF16 matrix remain separate checks.

Developers can run `python scripts/build_h3_workflow_bundle.py` from the repository after installing the panel's development dependencies. It validates canonical/visual parity and writes three deterministic ZIPs plus checksums to `dist/`. Sources are allowlisted: downloading guides or creating caches cannot silently add them to the ZIPs. When canonical assets change, regenerate visual graphs using native ComfyUI import/export and rerun parity checks.
