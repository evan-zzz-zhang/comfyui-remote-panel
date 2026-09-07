# Comfy Remote v0.4.8 H3 配套工作流

[English](README.md)

此可选集合提供 18 个工作流：**FL2VA / Ref2VA × original / LightX2V / v4step600 × Raw / Ollama / Qwen3.5**。Comfy Remote 的通用 ComfyUI API 工作流不依赖 H3。

## 选择下载包

| Release 附件 | 内容 | 用途 |
| --- | --- | --- |
| `comfy-remote-h3-panel-0.4.8.zip` | 18 份 canonical API 图和 manifest | 面板专用创建流程 |
| `comfy-remote-h3-comfyui-0.4.8.zip` | 18 份原生图形工作流 JSON | 在 ComfyUI 画布直接打开 |
| `comfy-remote-h3-nodes-0.4.8.zip` | 三个必要节点包及资料下载脚本 | 为上述两种工作流安装依赖 |

Release 同时提供 SHA256 校验文件。下载包不含模型、LoRA、参考素材、生成结果或官方提示词资料。

## 安装依赖

1. 使用 **ComfyUI 0.26.0 或更新版本**，具备原生 MiniMax H3、Qwen3.5 CLIP、音视频与动态输入节点支持。版本号不保证模型和节点齐全，运行前先处理缺失节点提示。
2. 安装 [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)，FL2VA Ollama 工作流使用其中的 `LazySwitchKJ`。
3. 将节点 ZIP 解压到临时准备目录，阅读[第三方说明](THIRD_PARTY_NOTICES.md)，在该目录运行 `python download_resources.py`。脚本只下载固定版本的官方提示词文本，核对 SHA256，拒绝覆盖内容有变化的已有文件，不下载模型、不执行下载的文本。此步骤需要联网；离线环境可在另一台电脑完成后复制准备好的节点目录。
4. 将 `custom_nodes` **内部**的三个目录复制到 ComfyUI 的 `custom_nodes`：`ComfyRemoteH3PromptWriter`、`H3OfficialSkillPromptWriter`、`H3Ref2VAQwen35`。等待生成结束再重启 ComfyUI。节点使用 ComfyUI 已有 Python 依赖（`torch`、`numpy`、`Pillow`、`av`），不要装到无关的系统 Python 中。
5. 如果已有本地修改版节点注册了相同的 H3 类名，先备份并禁用重复版本。只有不注册这些同名节点时，才可同时保留公开版 Prompt Writer 网页扩展。此包只暴露工作流节点，不附加 HTTP 路由或网页界面，也不需要修改 ComfyUI 核心文件。
6. 安装 H3 视频/音频 VAE、H3 生成模型、H3 文本编码器，以及加速模式对应的 LoRA。精确文件名和模型链接见各 canonical manifest 的依赖元数据。Qwen3.5 工作流还需要 `qwen3.5_4b_bf16.safetensors`；Ollama 工作流需要可连接的本地 Ollama 服务和所选模型（默认 `gemma4:e4b`）。模型遵循各自许可证。

## 搭配面板使用

Comfy Remote v0.4.8 已内置这 18 份 API 图和 manifest。安装好 ComfyUI 依赖后，使用现有 FL2VA/Ref2VA 选择器即可。面板 ZIP 便于检查、部署和复用，通常无需重复安装。

如需自定义部署，将 ZIP 中 `workflows` 的内容复制到 `[storage].workflow_dir` 指定的目录，保留 `family/mode/backend/manifest.json` 与 `workflow.json` 层级。同 ID 自定义资产会覆盖内置资产，因此先备份已有自定义内容。不要用图形 JSON 替换专用 manifest；通用 API 导入仍是独立功能。

## 在 ComfyUI 直接使用

打开或拖入 `comfyui/` 中的 JSON。在模型节点选择已安装模型，在图片/视频加载节点上传或选择自己的素材。`reference-image.png` 和 `reference-video.mp4` 是刻意不存在的占位文件。不同操作系统可能需要重新选择模型子目录。示例使用 INT8 H3 模型路径和固定种子，不会自动切换为 BF16。

FL2VA 示例连接首帧，需要尾帧时接入已有的可选参考输入。Ref2VA 示例连接一张图片和一个视频，可通过保留的可选集合输入扩展素材；扩展时保留音视频配对和归一化连线。在提示词节点修改自然语言需求。Ref2VA Qwen 示例中另有一份面板预处理后的角色请求快照：改变角色分工时也要修改该请求，或回到面板重新生成；独立画布不会执行面板的预处理逻辑。

## 验证与边界

18 个图形工作流均通过 ComfyUI 原生导入/导出，并与面板构建的脱敏 API 示例核对动态输入、连线和控件值；示例将提示词种子固定以便复现。既有真机验收覆盖 FL2VA 9/9、Ref2VA 9/9 INT8 生成、Qwen Ref2VA 角色替换、Ollama 简单角色，以及代表性 BF16 生成。Raw 自然语言理解和复杂角色识别仍属于模型能力边界。这不代表全部模型、硬件组合通过；全新安装后的 GPU 验收和完整 BF16 矩阵需单独验证。

开发者安装面板开发依赖后，可在仓库根目录运行 `python scripts/build_h3_workflow_bundle.py`，校验 canonical/图形一致性，并在 `dist/` 生成三个可复现 ZIP 和校验文件。节点源码使用明确清单，下载的资料和缓存不会自动混入 ZIP。canonical 资产变更后，应通过 ComfyUI 原生导入/导出更新图形文件，再执行一致性检查。
