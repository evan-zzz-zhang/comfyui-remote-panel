# FL2VA 工作流资产清单

这是 v0.4.7 的正式资产契约。9 个 canonical asset 通过 manifest 字段解析；
旧的 `h3-fl2va*` ID 继续保留，用于已有任务和 Retry 的兼容。

| 生成模式 | 原始提示词 | Ollama 提示词 | Qwen3.5 提示词 |
| --- | --- | --- | --- |
| original | `fl2va_original_raw` | `fl2va_original_ollama` | `fl2va_original_qwen35` |
| v4step600 | `fl2va_v4step600_raw` | `fl2va_v4step600_ollama` | `fl2va_v4step600_qwen35` |
| lightx2v | `fl2va_lightx2v_raw` | `fl2va_lightx2v_ollama` | `fl2va_lightx2v_qwen35` |

每个 canonical 目录包含：

```text
workflow.json
manifest.json
```

Manifest 明确声明 `family`、`generation_mode`、`prompt_backend`、
`input_mode`、参数绑定、输出节点、Prompt 捕获信息和推理配置契约。当前
内置主模型资产是真实可用的 INT8；`auto` 会解析到该资产。显式选择
FP16/BF16 前必须先由 manifest 声明对应变体，否则直接拒绝，不会静默改跑
INT8。

Prompt 捕获契约：

- `raw`：不生成标准化 Prompt；
- `ollama`：捕获 H3 `PreviewAny` 的 history 输出；
- `qwen35`：优先读取保存节点的 `standardized_prompt` metadata，失败时回退
  到 Qwen `PreviewAny` 的文本输出。

源码包仍保留 6 个历史 FL2VA 物理资产和 3 个历史 Ref2VA 资产。它们是兼容
资产，不是 canonical FL2VA 3 × 3 家族之外的新增组合。
