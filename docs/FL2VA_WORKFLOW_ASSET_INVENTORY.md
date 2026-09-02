# FL2VA Workflow Asset Inventory

This inventory is the v0.4.7 canonical asset contract. The nine canonical
assets are selected only through manifest fields; the older `h3-fl2va*` IDs
remain bundled as legacy compatibility records for existing jobs and retries.

| Generation mode | Raw prompt | Ollama prompt | Qwen3.5 prompt |
| --- | --- | --- | --- |
| original | `fl2va_original_raw` | `fl2va_original_ollama` | `fl2va_original_qwen35` |
| v4step600 | `fl2va_v4step600_raw` | `fl2va_v4step600_ollama` | `fl2va_v4step600_qwen35` |
| lightx2v | `fl2va_lightx2v_raw` | `fl2va_lightx2v_ollama` | `fl2va_lightx2v_qwen35` |

Each canonical directory contains:

```text
workflow.json
manifest.json
```

The manifest declares `family`, `generation_mode`, `prompt_backend`,
`input_mode`, parameter bindings, output node, prompt capture metadata, and
the inference profile contract. The current bundled main-model asset is INT8;
`auto` resolves to that asset. The 2026-09-02 local inventory contains
`MiniMax-H3/minimax_h3_fl2va_pruned_int8_convrot.safetensors`, but no matching
FL2VA FP16/BF16 main model. The available
`minimax_h3_ref2va_pruned_bf16.safetensors` is a Ref2VA weight and cannot be
bound to `MiniMaxH3ImageToVideo`. Therefore FP16/BF16 is explicitly disabled
until the compatible FL2VA weight is installed; a request cannot silently run
INT8.

Prompt capture contracts:

- `raw`: no standardized prompt is produced.
- `ollama`: the H3 `PreviewAny` history output is captured.
- `qwen35`: the save-node `standardized_prompt` metadata is preferred, with
  the Qwen `PreviewAny` text output as fallback.

The source package also keeps the six historical physical FL2VA assets and
the three historical Ref2VA assets. They are compatibility assets, not extra
members of the canonical FL2VA 3 × 3 family.
