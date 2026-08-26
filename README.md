# Comfy Remote

Comfy Remote 是一个手机优先的 ComfyUI 远程创作端。它不把完整 ComfyUI 搬到手机上，而是把本机已经调好的工作流转换成简单、一致的创作界面：选择工作流、添加参考素材、填写提示词、调整少量基础参数、提交任务并查看结果。

当前 v0.2 以单主机体验为目标，内置六个经审核的 MiniMax H3 FL2VA/Ref2VA 工作流，同时支持导入 ComfyUI API Workflow。导入后的图片或视频工作流会尽量自动识别基础输入；复杂节点参数默认留在 ComfyUI 中，不要求手机端用户理解 node/input。

## 移动端体验

主导航只有三个高频入口：

- **创作**：选择工作流、添加参考素材、输入提示词、调整基础生成设置并提交。
- **任务**：查看排队/运行状态、视频或图片结果、失败信息，以及“再次生成”。
- **设备**：查看 ComfyUI、GPU/显存、内存和存储状态，并按固定本机配置启动、关闭或重启 ComfyUI。

右上角设置入口包含工作流管理。内置 H3 工作流允许修改前端显示名称、启用或禁用；自定义工作流还支持高级映射、复制、导出和删除。

## 工作流兼容

v0.2 的移动端 UI 以“工作流需要哪些创作输入”来组织页面，而不是把 ComfyUI 节点直接暴露给用户。当前重点覆盖三类基准场景：

- **FL2VA**：提示词、可选首帧/尾帧、时长、画幅、分辨率，输出视频。
- **Ref2VA**：提示词、最多 9 张参考图、3 段参考视频、3 段参考音频、时长、画幅、分辨率，输出视频。
- **普通生图 / WAI 类工作流**：正面提示词、负面提示词、可选参考图、宽高/画幅、批次数量，输出一张或多张图片。

自定义工作流导入时，Comfy Remote 会优先识别正/负提示词、参考图片、宽高、批次数量和主要输出。无法可靠识别的内容仍可在“高级 · 手动节点映射”中处理。详见 [Remote Workflow 使用说明](docs/WORKFLOWS.md)。

## 核心能力

- 六个内置 MiniMax H3 FL2VA/Ref2VA 工作流。
- ComfyUI API Workflow 导入、自动基础输入识别、测试、启用/禁用、revision 与任务快照。
- 多任务 FIFO、实时阶段/采样进度、定向取消，以及载入原任务状态后重新生成。
- 图片、视频、音频和文件 artifact；视频支持 Range 播放/下载，图片任务支持多结果查看。
- SQLite 历史；“移出历史”默认只隐藏记录，物理清理使用显式 purge。
- NVIDIA GPU、显存、温度、功耗、内存、磁盘和 ComfyUI 状态。
- Windows 本机 ComfyUI 固定命令启动、关闭和重启。
- Tailscale Serve 身份头认证；除 `/healthz` 外没有匿名入口。
- 原生 HTML/CSS/JS，无 Node.js、React、Vue 或前端构建步骤。

## 要求

- Python 3.11 或更高版本。
- ComfyUI 0.26.0 或更高版本，面板与 ComfyUI 位于同一台机器。
- 对于内置 H3 工作流，需要清单中声明的模型和 LoRA。
- 默认远程访问方式为 Tailscale Serve；不要使用 Funnel，也不要把面板或 ComfyUI 8188 直接暴露到公网。

## 安装

```text
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[test]"
```

复制 `config.example.toml` 为不受 Git 跟踪的 `config.toml`，填写 ComfyUI 输入/输出目录、Tailscale HTTPS Origin 和允许登录的身份。所有相对路径都以配置文件所在目录为基准。

```text
.venv/Scripts/comfyui-remote-panel --config config.toml
tailscale serve --bg 8190
```

访问 `tailscale serve status` 显示的 HTTPS 地址。直接访问本机 8190 不会带 Tailscale 身份头，因此除健康检查外返回 403 是预期行为。若仅在本机回环使用，可选择 `auth.provider = "local"`。

Windows Portable 的逐步部署、身份确认和启动器集成见 [docs/WINDOWS_PORTABLE.md](docs/WINDOWS_PORTABLE.md)。发布前实机检查见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)。

## 配置与数据

- 面板强制监听 `127.0.0.1`。
- 上传保存到 ComfyUI 输入目录下的单层 `h3_remote/` 平铺目录；这是历史兼容存储名称，不代表产品仍只支持 H3。
- 输出由 workflow output binding 注册为通用 artifact；旧 H3 视频 `/video` 地址继续兼容。
- 每个任务保存工作流 revision、完整 workflow snapshot 和提交时的 input values；后续重命名、编辑或禁用工作流不会改变历史任务。
- 数据库位于配置的 `data_dir`；旧版 UUID 子目录会在启动时迁移到平铺目录，未登记文件只告警、不自动删除。
- 面板启动不依赖 ComfyUI 在线；ComfyUI 离线时页面、任务历史和设备操作仍可打开，无法生成的工作流会显示不可用状态。
- 设备控制默认关闭；启用 `[comfyui.control]` 后，面板只执行本机固定命令，并在关闭前核验监听进程身份。

## 开发与测试

```text
.venv/Scripts/python -m pytest
.venv/Scripts/python scripts/check_repository.py
```

GitHub Actions 覆盖 minimum-dependencies、Windows/Linux 与 Python 3.11/3.13，并验证 wheel 构建。真实 GPU 生成不属于 CI；v0.2 发布前至少应使用真实 ComfyUI 分别完成 FL2VA、Ref2VA 和一套普通生图/WAI API Workflow 的完整生成链路。

## English

**Comfy Remote** is a mobile-first companion for running trusted local ComfyUI workflows without exposing the full ComfyUI graph editor on a phone. The mobile creation surface is driven by workflow semantics such as prompts, references, dimensions, duration and output kind.

v0.2 ships six reviewed MiniMax H3 FL2VA/Ref2VA workflows and also supports imported ComfyUI API workflows. The importer attempts to recognize common image-generation inputs such as positive/negative prompts, reference images, width/height, batch size and primary output. Node-level mapping remains available as an advanced fallback rather than the default workflow.

It requires Python 3.11+, ComfyUI 0.26.0+, and same-host filesystem access. Tailscale Serve remains the recommended/default remote access provider. See [SECURITY.md](SECURITY.md), [docs/WORKFLOWS.md](docs/WORKFLOWS.md), and [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) before deployment or release.
