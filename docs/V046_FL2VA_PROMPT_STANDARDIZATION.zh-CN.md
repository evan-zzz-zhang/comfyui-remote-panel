# v0.4.6 FL2VA 提示词标准化

v0.4.6 继续保持 **一个 MiniMax H3 FL2VA 创作入口**，同时把两个产品级选择明确分开：

- 生成模式：`v4_600step`、`LightX2V`、`original`。
- 标准化提示词：`关闭`、`Ollama`、`ComfyUI`。

创作页不会暴露 6 个物理工作流。现有 3 个 FL2VA 工作流继续承担“关闭 / Ollama”路径，另外新增 3 个 bundled 工作流承担使用 Qwen3.5 4B 的 ComfyUI 标准化路径。

## 路由关系

| 生成模式 | 关闭 | Ollama | ComfyUI |
| --- | --- | --- | --- |
| original | `h3-fl2va` | `h3-fl2va` | `h3-fl2va-qwen35-4b` |
| LightX2V | `h3-fl2va-lightx2v` | `h3-fl2va-lightx2v` | `h3-fl2va-lightx2v-qwen35-4b` |
| v4_600step | `h3-fl2va-v4step600` | `h3-fl2va-v4step600` | `h3-fl2va-v4step600-qwen35-4b` |

对于现有物理工作流：

- “关闭”设置 `prompt_standardization=false`。
- “Ollama”设置 `prompt_standardization=true`，并继续使用用户选择的 Ollama 模型。
- “ComfyUI”直接切换到对应 Qwen 工作流，不依赖 Ollama 是否在线。

## Qwen 工作流契约

三套 ComfyUI 标准化工作流继续保持其对应现有工作流的生成模型、LoRA、sampler、scheduler、steps、H3 参考帧路由和 Panel 输出管理不变，只把提示词路径替换为：

- `qwen3.5_4b_bf16.safetensors`
- `H3InputResolverV4`
- `H3OfficialSkillPromptWriterQwen`
- Official H3 Skill 提示词契约

这些物理工作流中的 Qwen 标准化固定开启。v0.4.6 暂不增加第二个“ComfyUI 模型选择”控件。

标准化后的文本继续从 ComfyUI history 捕获。优先读取保存节点暴露的 `standardized_prompt` metadata；如果真实 ComfyUI history 没有把这段 metadata 暴露出来，则回退读取 `PreviewAny(177)` 中、直接来自 Qwen writer 最终送入 H3 的 Prompt。最终仍统一写入现有公开字段 `standardized_prompt`，不新增数据库 schema migration。

## 旧版本兼容

旧 FL2VA 请求和历史任务继续有效：

- `prompt_standardization=false` 映射为“关闭”。
- `prompt_standardization=true` 映射为“Ollama”。
- v0.4.2-v0.4.5 的 Retry 会根据物理 workflow 和历史 Boolean 推导新的三态选择。
- Qwen 任务 Retry 会恢复 `prompt_standardization_mode=comfyui`。

某个 Qwen 工作流缺失、不可用或被禁用，只影响对应的“生成模式 + ComfyUI”组合，不应影响同一生成模式的“关闭 / Ollama”。

## 界面行为

高级设置里原先可见的提示词标准化 Boolean 开关改成三态下拉框。旧 Boolean 仍作为内部兼容状态保留，用来复用已经验收过的 Prompt 必填逻辑和 v0.4.5 Ollama 模型选择逻辑，不改变其他创作界面。

只有选择“Ollama”时显示 Ollama 模型字段。标准化方式会保存在浏览器 localStorage 中。

任务卡继续保持紧凑布局，但会补充两个可选运行标签：使用加速方案时显示 `LightX2V` 或 `v4_600step`，使用提示词标准化时显示 `Ollama` 或 `Qwen3.5 4B`。`original` 和“关闭标准化”不额外占用标签空间。

任务卡顶部的“生成”时间表示从 ComfyUI 真正开始执行到任务结束的总生成时间，不包含排队等待。H3 sampler 的耗时单独称为“采样”，只在运行进度和任务详情中显示，避免把采样时间误认为完整任务耗时。

## 自动化覆盖

CI 覆盖：

- 3 × 3 共 9 种路由组合；
- 旧 Boolean 请求兼容；
- Qwen 标准化 Prompt history 捕获，包括保存节点 metadata 与 PreviewAny 回退路径；
- Retry 标准化后端恢复；
- 单条 Qwen workflow 禁用隔离；
- 三套 Qwen workflow 的生成参数与模型依赖；
- 前端脚本注入、三态选择、物理 workflow 隐藏和 Qwen route availability；
- 任务卡总生成时间、采样耗时和运行标签；
- package 内容、minimum dependencies、repository safety、Windows/Linux、Python 3.11/3.13。

## 真机验收

v0.4.6 PR 在进入 release-ready 前，需要在目标 Windows / ComfyUI 机器完成：

1. `v4_600step + 关闭` 正常完成。
2. `v4_600step + Ollama` 正常完成，并捕获 Ollama 标准化 Prompt。
3. `v4_600step + ComfyUI` 实际加载 Qwen3.5 4B、捕获 Qwen 标准化 Prompt，并完成 H3 生成。
4. `LightX2V + ComfyUI` 正常完成。
5. `original + ComfyUI` 正常完成。
6. 对一个 ComfyUI 标准化任务执行 Retry，恢复生成模式、ComfyUI 后端、Prompt、参考素材、seed 和采样参数。
7. 验证 Qwen 在进入 H3 采样前具有合理的释放 / offload 行为，不产生可避免的显存叠加 OOM。
8. 手机端确认仍只有一个 FL2VA 入口，高级设置显示三态选择，并且 Ollama 模型字段只在 Ollama 模式出现。
9. 任务卡显示总生成耗时，并按实际组合显示简洁的加速 / 标准化标签。

真实 GPU、Custom Node 和手机浏览器行为无法由 CI 证明，验收结果需要与自动化结果分开记录。
