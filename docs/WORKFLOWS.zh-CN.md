# Comfy Remote 工作流 / Configurator 2.0 使用说明

[English](WORKFLOWS.md) | **简体中文**

## 设计原则

Comfy Remote 不尝试在手机上重新实现 ComfyUI，也不会要求所有工作流长成同一种结构。

工作流应该先在本机 ComfyUI 中调好并成功运行；Comfy Remote 负责分析它实际具有的创作能力，把适合远程修改的输入映射到手机界面，并保留真实 API Workflow 图用于提交。

默认流程：

```text
ComfyUI 工作流
→ 导出 API Workflow
→ Configurator 2.0 分析
→ 用户确认少量不确定项
→ Preflight
→ 保存 / 启用
→ Runtime Test
→ 创作页使用
```

### H3 Ref2VA 运行说明

- 创作页默认选择虚拟入口 `h3-fl2va-group`；具体物理资源 ID 只属于实现细节。
- Ref2VA 使用参考视频画幅时，比例由视频本身推导。生成提示词中的 `9:16` 是画幅比例，不是时间戳。
- Ollama 提示词标准化依赖当前版本的 H3 Prompt Writer 插件。更新插件后需要重启 ComfyUI，校验器修改才会加载。

核心原则：

- 不要求一定存在 `width`、`height`、`batch_size`。
- 不因为节点 ID、模型、LoRA、Sampler 出现在 JSON 中就自动把它们暴露到手机主界面。
- 不为了适配 UI 静默改写工作流图。
- 自动识别不确定时，优先给出候选/置信度或要求显式映射，而不是假装确定。

## 导入 API Workflow

1. 先在本机 ComfyUI 中确认目标工作流能够正常运行。
2. 使用 ComfyUI 的 **API Format** 导出 JSON。普通 UI Workflow JSON 不是同一种格式。
3. 在 Comfy Remote 进入 **设置 → 工作流 → 导入工作流**。
4. 选择 API Workflow JSON。
5. Configurator 2.0 分析节点 schema、连接关系、输入/输出语义和可配置参数。
6. 对多个候选、低置信度或复杂自定义节点进行确认/手动映射。
7. 保存并启用。
8. 执行真实 Runtime Test。

如果 ComfyUI 当前前端看不到 API 格式导出入口，通常需要在 Settings 中启用 Dev Mode / Developer Mode Options；不同 ComfyUI frontend 版本的具体 wording 可能略有不同。

## Configurator 2.0 如何识别工作流

v0.3 不是单纯按节点名字写死规则，而是组合三类证据。

### Schema

从当前 ComfyUI `/object_info` 读取节点定义，理解：

- 输入名与类型；
- 数值范围 / step；
- 枚举；
- 是否为连接输入或字面输入；
- custom node 对外声明的 schema。

这让 Configurator 能区分“一个叫 `width` 的字符串”和“真正由节点 schema 声明的整数尺寸输入”。

### Graph

分析 API Workflow 的节点连接关系，用于判断：

- sampler 的 positive / negative 条件从哪里来；
- LoadImage / LoadVideo / LoadAudio 如何进入生成路径；
- latent/尺寸是否继承自输入素材；
- 哪些节点是真正参与主要输出的路径；
- SaveImage / SaveVideo / 其他输出节点与主要 artifact 的关系。

因此 img2img 不需要被强行改写成包含 `EmptyLatentImage` 的 txt2img 结构。

### Heuristic fallback

当 schema 和图连接仍不足以唯一确定语义时，可以使用保守的 heuristic fallback。

Fallback 不是“猜完就当真”。不确定结果应体现置信度，并允许用户在 Configurator 中确认或用高级映射覆盖。

## 能力与参数是两回事

Configurator 2.0 会尽量区分：

- **Workflow capability**：这个工作流需要什么输入、产生什么输出、属于 image/video/audio/mixed 哪一类能力。
- **Editable parameter**：哪些字面输入适合让远程用户修改。

例如：

- 一个 img2img 工作流可能要求 1 张图片，但没有可调 `width / height`，因为尺寸来自输入图片。
- 一个视频 custom node 可能内部管理尺寸和时长，只暴露 prompt 与参考视频。
- 一个工作流可以完全没有 `batch_size`，仍然是合法、可用的工作流。

手机 UI 应根据能力和显式可编辑参数组合，而不是反过来强迫工作流迁就固定表单。

## Preflight

兼容性检查使用 `PASS / WARN / FAIL`，覆盖多个层级：

1. **JSON / Structure** — API Workflow 是否可解析、节点结构是否合法。
2. **Nodes** — `class_type` 是否存在于当前 ComfyUI `/object_info`。
3. **Inputs** — 必需媒体槽、连接输入和字面输入是否合理。
4. **Parameters** — 自动识别/手动映射的参数是否符合 schema。
5. **Outputs** — 是否能确定可追踪的主要 artifact 输出。
6. **Runtime** — 真实提交后是否成功完成并产出预期结果。

`WARN` 表示存在不确定、可选依赖或需要注意的条件；`FAIL` 表示当前配置存在阻塞性问题。

导入成功只证明前面的静态分析能够完成，**不代表模型、显存、路径和第三方节点运行时一定成功**。

## 媒体输入

普通自定义工作流可以识别/声明固定媒体槽，例如：

- image；
- video；
- audio；
- file。

必需媒体槽会在提交前校验。没有提供必需输入时，创作页不会假装可以正常运行。

内置 H3 Ref2VA 使用自己的 schema v2 媒体集合能力，但这不是普通 Workflow 必须遵循的结构。

## 提示词

对于常见采样图，正/负提示词会优先根据 sampler 的 `positive` / `negative` 图连接向上追踪，而不是仅凭两个相同的 CLIPTextEncode 名称或节点顺序判断。

自定义节点若把提示词封装在自己的 schema 中，也可以通过 schema/高级映射成为可编辑输入。

## 尺寸、画幅和批次

`width / height / batch_size` 是常见参数，不是核心协议要求。

只有当工作流实际存在可安全修改的对应输入时，创作页才应暴露它们。

如果尺寸来自上传图片、latent 连接、custom node 内部策略或其他节点，Configurator 可以把它识别为工作流能力的一部分，而不需要伪造一个宽高参数。

## 高级 · 手动节点映射

自动识别不可能覆盖所有第三方 Custom Node。

高级映射允许用户显式选择需要远程修改的**字面输入**。连接到其他节点的输入不会因为高级模式而被随意断开；模型路径、内部文件路径、敏感字段等也不应自动成为手机参数。

高级映射是兼容性回退机制，不是要求普通用户理解所有 node ID。

## 输出与 artifact

运行结果统一登记为 artifact，可包含：

- image；
- video；
- audio；
- file。

单图任务使用适合查看的结果布局；多输出任务可以保留 gallery 行为。视频继续支持浏览器播放/Range 请求与下载。

如果工作流存在多个可能输出，Configurator 应确认主要输出，而不是默认把所有输出都当作主结果。

## Runtime Test

“测试”会真实向本机 ComfyUI 提交当前 revision 的 Workflow，并消耗实际 GPU/模型资源。

Runtime Test 用于发现静态分析无法证明的问题，例如：

- 模型文件缺失；
- custom node 运行时报错；
- CUDA OOM；
- 输出节点没有产生预期 artifact；
- 本机路径/节点环境与 Workflow 不一致。

Runtime 结果与具体 workflow revision 绑定。编辑或导入新 revision 后，不应继承旧 revision 的 Runtime PASS。

## Workflow revision 与历史任务

每次保存修改都会形成 revision。任务保存提交时使用的 workflow ID / revision / snapshot / input values，因此后续编辑、改名或禁用当前工作流不会篡改历史任务依据。

内置工作流不能删除，但可调整前端显示名称；自定义工作流可编辑、复制、导出和删除。

## Remote Workflow Package

导出 Package ZIP 可包含：

- `workflow-api.json`
- `remote-config.json`
- `metadata.json`

Package 不应包含模型、LoRA、真实上传素材、生成结果、token、password、API key 或本机绝对路径。

导入时对未知文件和明显敏感字段进行限制，但公开分享前仍应人工检查内容。

## Seed — v0.3 简单规则

v0.3 尚未引入独立 Seed Policy。

当前规则：

- seed 留空：随机；
- 显式数字（包括 `0`）：固定为该数字。

`randomize / fixed / increment` 等策略计划作为后续独立设计，不通过特殊 seed 数字暗中表达。

## H3 的位置

内置六个 MiniMax H3 工作流是 Bundled / Verified examples，用于提供已验证的视频工作流体验和回归样本。

**H3 不是 Comfy Remote 架构前提。**

没有 H3 custom node 或模型时，对应内置工作流可以显示 `WARN` / unavailable，但普通 ComfyUI API Workflow 仍应正常导入、测试和生成。

## 反馈兼容性问题

先运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

然后使用 GitHub 的 **Workflow Compatibility** Issue 模板。

不要公开上传未经检查的 Workflow、真实提示词、素材、配置文件、数据库或完整日志。API Workflow 也可能包含模型名、本机路径或业务提示词，请先检查再分享。
