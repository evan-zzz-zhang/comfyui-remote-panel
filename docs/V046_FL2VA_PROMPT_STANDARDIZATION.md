# v0.4.6 FL2VA Prompt Standardization

v0.4.6 keeps **one MiniMax H3 FL2VA creation entry** while separating two product-level choices:

- Generation mode: `v4_600step`, `LightX2V`, or `original`.
- Prompt standardization: `Off`, `Ollama`, or `ComfyUI`.

The creation page does not expose six physical workflows. The existing three FL2VA workflows continue to serve the Off/Ollama paths, and three additional bundled workflows serve the ComfyUI path with Qwen3.5 4B.

## Routing

| Generation mode | Off | Ollama | ComfyUI |
| --- | --- | --- | --- |
| original | `h3-fl2va` | `h3-fl2va` | `h3-fl2va-qwen35-4b` |
| LightX2V | `h3-fl2va-lightx2v` | `h3-fl2va-lightx2v` | `h3-fl2va-lightx2v-qwen35-4b` |
| v4_600step | `h3-fl2va-v4step600` | `h3-fl2va-v4step600` | `h3-fl2va-v4step600-qwen35-4b` |

For the existing physical workflows, Off sets `prompt_standardization=false`; Ollama sets it to true and preserves the selected Ollama model. The ComfyUI route selects the corresponding Qwen workflow and does not depend on Ollama.

## Qwen workflow contract

The three ComfyUI-standardized workflows keep the same generation model, LoRA, sampler, scheduler, steps, H3 reference-frame routing, and Panel output handling as their existing counterparts. Their prompt path uses:

- `qwen3.5_4b_bf16.safetensors`
- `H3InputResolverV4`
- `H3OfficialSkillPromptWriterQwen`
- the Official H3 Skill prompt contract

The Qwen path is fixed on for these physical workflows. v0.4.6 does not expose a second ComfyUI-model selector.

The standardized text is captured from ComfyUI history. Save-node metadata is preferred; when real ComfyUI history does not expose that metadata, the `PreviewAny(177)` output wired to the Qwen writer's final H3 prompt is used as a fallback. The value continues to use the existing public `standardized_prompt` field, with no database schema migration.

## Compatibility

Legacy FL2VA requests and Jobs remain valid:

- `prompt_standardization=false` maps to Off.
- `prompt_standardization=true` maps to Ollama.
- Existing v0.4.2-v0.4.5 Retry data is inferred from the physical workflow plus the stored Boolean.
- Qwen Jobs restore `prompt_standardization_mode=comfyui` on Retry.

Missing or disabled Qwen workflows affect only the matching `generation mode + ComfyUI` route. They do not disable the same generation mode with Off or Ollama.

## UI

The previous visible prompt-standardization Boolean is replaced by a three-state selector in Advanced Settings. The old Boolean remains an internal compatibility state so the accepted prompt-required behavior and the v0.4.5 Ollama selector can be reused without changing unrelated creation UI.

The Ollama model field is visible only when `Ollama` is selected. The selected standardization mode is remembered in browser local storage.

Task cards keep the compact layout while adding up to two optional runtime tags: `LightX2V` or `v4_600step` for an acceleration mode, and `Ollama` or `Qwen3.5 4B` for prompt standardization. `original` and Off do not consume extra tag space.

The task-card `生成` duration is the total execution time from when ComfyUI actually starts the Job until it finishes; queue waiting is excluded. H3 sampler time is labeled `采样` and is shown only in live progress and task details so sampler duration is not mistaken for total generation time.

## Automated coverage

CI covers:

- all 3 × 3 routing combinations;
- legacy Boolean compatibility;
- Qwen standardized-prompt history capture, including save-metadata and PreviewAny fallback paths;
- Retry backend restoration;
- per-route workflow disable isolation;
- Qwen workflow tuning and model dependencies;
- frontend injection, selector states, hidden physical workflows, and Qwen-route availability;
- task-card total generation time, sampler duration, and runtime tags;
- package contents, minimum dependencies, repository safety, Windows/Linux, and Python 3.11/3.13.

## Real-machine acceptance

Before the v0.4.6 PR is considered release-ready, validate on the target Windows/ComfyUI machine:

1. `v4_600step + Off` completes normally.
2. `v4_600step + Ollama` completes and captures the Ollama-standardized prompt.
3. `v4_600step + ComfyUI` loads Qwen3.5 4B, captures the Qwen-standardized prompt, and completes H3 generation.
4. `LightX2V + ComfyUI` completes.
5. `original + ComfyUI` completes.
6. Retry from a ComfyUI-standardized Job restores the generation mode, ComfyUI backend, prompt, media, seed, and tuning.
7. Qwen memory is released/offloaded sufficiently before H3 sampling to avoid an avoidable OOM.
8. On a phone, Advanced Settings shows one FL2VA entry, the three-state selector, and the Ollama model field only for Ollama.
9. Task cards show total generation time and the compact acceleration/standardization tags for the actual route.

Real GPU/custom-node and mobile results must be recorded separately from CI because CI cannot prove those runtime properties.
