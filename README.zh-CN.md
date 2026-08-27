# Comfy Remote

[English](README.md) | **简体中文**

**从手机运行你本地的 ComfyUI 工作流。**

> **当前状态：v0.3.0 Public Beta。**
>
> 核心远程生成、通用 ComfyUI API Workflow、Windows Setup、Tailscale 远程访问、Doctor 诊断和 Windows 登录自启动已经可用。高级故障恢复、多主机、Wake-on-LAN 等能力尚未实现。

Comfy Remote 是一个手机优先的 ComfyUI 远程创作面板。它运行在 ComfyUI 所在的 Windows 电脑上，把已经在本机验证过的 **ComfyUI API Workflow** 转成适合手机使用的创作界面：选择工作流、添加素材、填写提示词、提交任务、查看结果。

v0.3 的重点是 **Public Readiness + Configurator 2.0**：第一次安装不需要手工编写 TOML，也不要求 MiniMax H3 环境；陌生 API Workflow 会通过 schema、图连接关系和保守的 heuristic fallback 分析能力与可编辑参数，再经过 Preflight 和真实 Runtime Test 验证。

## 能做什么

- 导入普通 ComfyUI **API Workflow**，分析工作流能力、媒体输入、提示词、可配置参数和主要输出。
- 使用 **Schema + Graph + heuristic fallback**，而不是要求所有工作流都必须存在 `width`、`height`、`batch_size` 等固定字段。
- Configurator 2.0 对不确定映射提供显式确认和高级手动映射，不会为了适配 UI 静默改写工作流图。
- 支持图片 / 视频 / 音频 / 文件 artifact 与任务历史。
- 支持提交、排队、实时进度、取消、再次生成、结果查看与下载。
- 提供 `setup`、`start / stop / restart / status`、`doctor` 和 Windows 登录自启动命令。
- Windows Portable ComfyUI 可识别已有启动脚本并保留实际启动参数，例如 `--enable-manager`、`--use-sage-attention`。
- 默认推荐使用 Tailscale Serve 从手机访问；Panel 与 ComfyUI 仍只监听本机。
- Web 面板支持 **简体中文 / English** 切换，并记住本机浏览器偏好。
- 内置六个 MiniMax H3 工作流作为 **Bundled / Verified examples**；没有 H3 节点或模型不会阻止 Panel 使用自己的 Workflow。

## Quick Start — Windows

### 前提

- Windows 10/11。
- **稳定版** Python 3.11 或更高版本；不建议/不支持 alpha、beta、RC 预发行 Python 作为公开安装路径。
- Git for Windows。
- 一套已经能在本机正常生成的 ComfyUI。
- 如果要手机远程访问：电脑和手机安装 Tailscale，并登录同一个 tailnet。

第一次使用者建议直接看完整的 [Windows 从零开始教程](docs/GETTING_STARTED_WINDOWS.zh-CN.md)。其中包含 Git/Python/Tailscale 准备、Setup 每一步怎么选、API Workflow 怎么导出，以及第一次手机生成成功的完整流程。

### 安装

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
.\scripts\windows\Install-ComfyRemote.ps1
```

安装脚本会检查 Python、创建 `.venv`、安装 Comfy Remote，然后进入 Setup 向导。

Setup 完成后：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

如果 Setup 已配置 Tailscale Serve，手机打开向导显示的 `https://…ts.net` 地址。

## Workflow compatibility

在 ComfyUI 中先确认目标工作流能够正常运行，然后导出 **API Workflow JSON**。普通的 UI Workflow JSON 不是同一种格式。

Configurator 2.0 的兼容性分析不是“找几个固定节点”，而是组合以下信息：

1. **JSON / Structure** — 是否为可解析的 API Workflow 节点结构。
2. **Schema** — 使用当前 ComfyUI `/object_info` 判断节点输入类型、枚举、数值范围和 custom node 能力。
3. **Graph** — 根据节点连接关系判断 prompt、媒体输入、尺寸来源、sampler 路径和输出语义。
4. **Heuristic fallback** — schema/graph 仍不足时进行保守推断，并标记置信度，而不是静默猜测。
5. **Preflight** — 汇总 JSON / Node / Input / Parameter / Output / Runtime 的 `PASS / WARN / FAIL`。
6. **Runtime Test** — 最后真实提交一次 ComfyUI 任务；模型文件、显存和第三方节点运行时行为仍以真实结果为准。

因此一个合法的 img2img 工作流可以没有 `EmptyLatentImage`，一个工作流也可以完全没有远程可调的 `width / height / batch_size`。Comfy Remote 会暴露它实际具有、且能够安全识别或由用户明确映射的创作输入。

详见 [Workflow / Configurator 2.0 说明](docs/WORKFLOWS.zh-CN.md)。

## Doctor / Feedback

遇到问题先运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

提交 GitHub Issue 时优先附：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

报告使用 `PASS / WARN / FAIL`，并自动脱敏用户目录、邮箱、Tailscale 主机名和明显 secret 值。仍建议公开提交前人工检查一次报告。

**如果你不用 MiniMax H3，内置 H3 工作流显示不可用或 Doctor 出现 H3 `WARN` 可以忽略。** 这不代表 Comfy Remote 安装失败。

常见问题见 [Troubleshooting](docs/TROUBLESHOOTING.zh-CN.md)。

## Tailscale security model

推荐链路：

```text
Phone → Tailscale HTTPS Serve → 127.0.0.1:8190 Comfy Remote → 127.0.0.1:8188 ComfyUI
```

- Panel 强制监听 `127.0.0.1:8190`。
- ComfyUI 保持本机 `8188`。
- Tailscale auth 模式依据 Serve 注入的登录身份头授权。
- 不要使用 Funnel，也不要把 8190 或 8188 直接暴露到公网。
- 第三方 ComfyUI Custom Node 仍是本机代码执行边界，Comfy Remote 不对它们做沙箱隔离。

安全细节见 [SECURITY.md](SECURITY.md)。

## Known limitations — v0.3 Public Beta

- **Windows 10/11 是当前主要验证平台。** Linux 参与 CI，但公开安装和真机使用路径目前以 Windows 为主。
- **Tailscale 是当前主要远程传输方式。** 核心架构不要求永远绑定 Tailscale，但其他远程 transport 尚未形成同等级公开安装路径。
- **ComfyUI 严重崩溃后的自动恢复仍有限。** Panel 可以启动、停止、重启其管理的 ComfyUI，但 GPU OOM、驱动异常、进程树异常等场景还没有完整 watchdog / recovery 策略。
- **没有 Wake-on-LAN。** 电脑睡眠、关机后的机外唤醒不属于 v0.3。
- **没有多主机。** 当前一个 Panel 对应本机一套 ComfyUI。
- **第三方 Custom Node 兼容性取决于 schema 和真实运行。** Configurator 2.0 会尽量分析，但不能保证所有第三方节点都能被自动理解。
- **Seed Policy 尚未独立设计。** v0.3 保持“留空 = 随机；显式数字（包括 0）= 固定”的简单规则。

后续执行基线见 [TODO / Roadmap](docs/TODO.md)。

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

兼容旧前台启动方式：

```powershell
comfyui-remote-panel --config config.toml
```

## Development

```powershell
python -m pytest
python scripts/check_repository.py
python -m build
```

CI 配置覆盖 Windows / Linux、Python 3.11 / 3.13 和 minimum-dependencies。真实 GPU、陌生 Windows、手机访问和第三方节点不能完全由 CI 代替。

贡献前请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## Documentation

- [Windows 从零开始](docs/GETTING_STARTED_WINDOWS.zh-CN.md)
- [Troubleshooting](docs/TROUBLESHOOTING.zh-CN.md)
- [Workflow / Configurator 2.0 说明](docs/WORKFLOWS.zh-CN.md)
- [Public Readiness Acceptance](docs/PUBLIC_READINESS_ACCEPTANCE.md)
- [TODO / Roadmap](docs/TODO.md)
- [Security](SECURITY.md)
