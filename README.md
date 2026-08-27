# Comfy Remote

**Run your local ComfyUI workflows from your phone.**

Comfy Remote 是一个手机优先的 ComfyUI 远程创作面板。它运行在 ComfyUI 所在的 Windows 电脑上，把已经验证过的 ComfyUI API Workflow 转成适合手机使用的创作界面：选择工作流、添加素材、填写提示词、提交任务、查看结果。

v0.3 Phase 1 的重点是 **Public Readiness**：第一次使用不再要求手工编写 TOML，也不再把 MiniMax H3 环境当成安装前提。

## What it does

- 导入普通 ComfyUI API Workflow，并尽量识别提示词、参考图、宽高、批次和主要输出。
- 支持图片 / 视频 / 音频 / 文件 artifact 与任务历史。
- 支持提交、排队、实时进度、取消、再次生成、结果查看与下载。
- 提供 `setup`、`start / stop / restart / status`、`doctor` 和 Windows 登录自启动命令。
- 默认推荐使用 Tailscale Serve 从手机访问，Panel 与 ComfyUI 仍只监听本机。
- 内置六个 MiniMax H3 工作流作为 **Bundled / Verified examples**；缺少 H3 节点或模型只会让对应工作流不可用，不会阻止 Panel 启动或使用自己的 Workflow。

## Quick Start — Windows

前提：这台电脑上的 ComfyUI 已经能正常生成，且安装了 Python 3.11+。

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
.\scripts\windows\Install-ComfyRemote.ps1
```

安装脚本会创建 `.venv`、安装 Comfy Remote，然后进入首次配置向导。Setup 会尝试找到 ComfyUI、生成配置，并可选配置 Tailscale Serve 与 Windows 登录自启动。

完成后：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

如果 setup 配置了 Tailscale Serve，使用手机访问向导显示的 `https://…ts.net` 地址。

完整逐步教程见 [Windows 快速开始](docs/GETTING_STARTED_WINDOWS.md)。

## Requirements

- Windows 10/11 是当前公开部署的主要目标。
- Python 3.11 或更高版本。
- ComfyUI 0.26.0 或更高版本。
- Panel 与目标 ComfyUI 位于同一台电脑，并能读写 ComfyUI `input / output`。
- 手机远程访问推荐 Tailscale；本机回环调试可以使用 `local` auth。

**不要求 MiniMax H3、H3 LoRA 或 H3 custom node。**

## CLI

```text
comfyui-remote-panel setup

comfyui-remote-panel start
comfyui-remote-panel stop
comfyui-remote-panel restart
comfyui-remote-panel status

comfyui-remote-panel doctor
comfyui-remote-panel doctor --report

comfyui-remote-panel autostart install
comfyui-remote-panel autostart status
comfyui-remote-panel autostart remove
```

v0.2 的前台启动方式仍然兼容：

```powershell
comfyui-remote-panel --config config.toml
```

## Workflow compatibility

在 ComfyUI 中先确认工作流能够正常运行，然后使用 **API Workflow** 格式导出。

Comfy Remote 的兼容性判断分四层：

1. **JSON** — 文件必须可解析，并具有 API Workflow 节点结构。
2. **Node** — 检查工作流使用的 `class_type` 是否存在于当前 ComfyUI `object_info`。
3. **Input / Output** — 尝试识别 prompt / negative、图片或视频输入、width / height / batch 与主要输出；复杂参数可以手动映射。
4. **Runtime** — 最终“测试”会真实提交一次 ComfyUI 任务；模型路径、显存、自定义节点运行时异常仍以真实运行结果为准。

详见 [Workflow 说明](docs/WORKFLOWS.md)。

## Doctor / Feedback

遇到问题先运行：

```powershell
comfyui-remote-panel doctor
```

提交 GitHub Issue 时优先附：

```powershell
comfyui-remote-panel doctor --report
```

报告使用 `PASS / WARN / FAIL`，并自动脱敏用户目录、邮箱、Tailscale 主机名和明显 secret 值。H3 缺依赖属于 `WARN`；ComfyUI API 不通或 input 不可写属于 `FAIL`。

常见问题见 [Troubleshooting](docs/TROUBLESHOOTING.md)。

## Tailscale security model

推荐链路：

```text
Phone → Tailscale HTTPS Serve → 127.0.0.1:8190 Comfy Remote → 127.0.0.1:8188 ComfyUI
```

- Panel 强制监听 `127.0.0.1:8190`。
- ComfyUI 保持本机 `8188`。
- Tailscale auth 模式依据 Serve 注入的登录身份头授权。
- 不要使用 Funnel，也不要把 8190 或 8188 直接暴露到公网。

安全细节见 [SECURITY.md](SECURITY.md)。

## Current limitations

v0.3 Phase 1 **不包含**：

- 生成现场恢复增强；
- 视频缩略图专项；
- 高清参考图自动压缩；
- Windows 睡眠 / 关机 / 系统重启；
- Wake-on-LAN；
- 多主机。

这些能力不会为了 Public Readiness 混入本阶段。

## Development

```powershell
python -m pytest
python scripts/check_repository.py
python -m build
```

CI 覆盖 Windows / Linux、Python 3.11 / 3.13 和 minimum-dependencies。真实 GPU 与陌生 Windows 部署不能由 CI 代替；发布前必须执行 [Public Readiness Acceptance](docs/PUBLIC_READINESS_ACCEPTANCE.md)。

## Documentation

- [Windows 快速开始](docs/GETTING_STARTED_WINDOWS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Workflow 说明](docs/WORKFLOWS.md)
- [Public Readiness Acceptance](docs/PUBLIC_READINESS_ACCEPTANCE.md)
- [执行 TODO](docs/TODO.md)
- [Security](SECURITY.md)
