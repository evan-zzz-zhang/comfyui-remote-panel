# Comfy Remote

[English](README.md) | **简体中文**

**从手机运行你本地的 ComfyUI 工作流。**

> **当前状态：v0.4.6 Public Beta。**
>
> 通用 ComfyUI API Workflow、手机创作、历史素材 Retry、H3 FL2VA 统一生成模式、已登记生成产物与历史同步、关闭/Ollama/ComfyUI 三态提示词标准化、受控强制关闭、SageAttention 运行状态、任务状态 reconciliation 加固、Windows 环境自愈安装、Windows Setup、Tailscale 远程访问、Doctor 诊断和 Recovery Lite 已可用。完整自动 watchdog、多主机和 Wake-on-LAN 尚未实现。

Comfy Remote 是一个手机优先的 ComfyUI 远程创作面板。它运行在 ComfyUI 所在的 Windows 电脑上，把已经在本机验证过的 **ComfyUI API Workflow** 转成适合手机使用的创作界面：选择工作流、添加素材、填写提示词、提交任务、查看结果。

当前 v0.4.6 基线在 **Public Readiness + Configurator 2.0** 之上补齐了 Specialized / Generic 创作边界、Seed Policy、参考图分辨率预处理、受控人工恢复、历史参考素材 Retry 连续性、H3 FL2VA 产品级模式路由、更稳健的任务最终状态 reconciliation、Windows 环境自愈、生成产物与历史记录同步，以及 H3 FL2VA 多后端提示词标准化能力，同时继续避免静默改写陌生工作流，也不把 ComfyUI 本身直接暴露到网络。

## 能做什么

- 导入普通 ComfyUI **API Workflow**，分析工作流能力、媒体输入、提示词、可配置参数和主要输出。
- 使用 **Schema + Graph + heuristic fallback**，而不是要求所有工作流都必须存在 `width`、`height`、`batch_size` 等固定字段。
- Configurator 2.0 对不确定映射提供显式确认和高级手动映射，不会为了适配 UI 静默改写工作流图。
- 支持图片 / 视频 / 音频 / 文件 artifact 与任务历史。
- 支持提交、排队、实时进度、取消、再次生成、结果查看与下载。
- Retry 时可恢复历史参考素材的真实预览，不要求手机重新选择或上传同一文件；retained 素材仍可显式替换或删除。
- 图片产物存在时，任务卡可显示实际输出宽、高、格式与文件大小。
- 对已经登记过 output artifact 的 Job，Panel 会检查对应受管本地生成产物；如果某个产物被删除或移走，就移除失效 artifact 引用；当该 Job 的全部已登记生成产物都不存在后，对应历史记录自动移除。从未登记过 output 的失败/中断任务不会仅因为“没有文件”被删除。
- 提供 `randomize / fixed / increment` Seed Policy 与参考图分辨率预处理；Generic 控件只来自真实 Workflow binding。
- 把内置 H3 FL2VA 物理工作流收敛到一个创作入口，通过 `v4_600step`、`LightX2V`、`original` 三种生成模式选择，同时仍由底层物理工作流的启用/禁用状态决定是否可用。
- H3 FL2VA “标准化提示词”是三态高级设置：`关闭`、`Ollama`、`ComfyUI`。Ollama 保留可配置模型（默认 `gemma4:e4b`）；ComfyUI 路由到内置 Qwen3.5 4B 工作流。Retry 会恢复实际使用的后端，两种标准化方式都把结果保存到同一个任务详情字段。
- 任务详情在可用时区分排队等待、标准化提示词、H3 采样和总执行时间；任务卡只在有意义时显示 `LightX2V`、`v4_600step`、`Ollama`、`Qwen3.5 4B` 标签。
- 加固任务状态 reconciliation：不完整 ComfyUI history 不再直接算失败；最终 history 尚未完全落盘时，明确的 `execution_success` 仍作为成功证据。
- 提供 Recovery Lite 受控恢复能力；当 Panel 没有有效进程记录、但能够唯一安全识别当前 ComfyUI 监听进程时，可提供“强制关闭”，不会按模糊 `python.exe` 批量结束进程。
- 设备概览只在当前实际核验到的 ComfyUI 监听进程命令行包含 `--use-sage-attention` 时显示 `SageAttention` 状态，不用配置文件冒充运行态。
- 提供 `setup`、`start / stop / restart / status`、`doctor` 和 Windows 登录自启动命令。
- Windows 安装器会真实启动并检查已有项目 `.venv`；如果环境已损坏，会先备份再重建，不会继续复用坏环境，也不会把全局 Python 静默当成长期开机运行环境。
- Windows Portable ComfyUI 可识别已有启动脚本并保留实际启动参数，例如 `--enable-manager`、`--use-sage-attention`。
- 默认推荐使用 Tailscale Serve 从手机访问；Panel 与 ComfyUI 仍只监听本机。
- 公共文档提供 English / 简体中文；当前 Web Panel 保持已验收的中文稳定 UI 基线。
- 内置九个 MiniMax H3 工作流作为 **Bundled / Verified examples**；没有 H3 节点或模型不会阻止 Panel 使用自己的 Workflow。

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

安装脚本会先检查基础 Python；如果项目已有 `.venv`，会真实启动它并做健康检查。健康环境直接复用，损坏环境会先重命名为 `.venv.broken-时间戳` 备份，再创建新的 `.venv`。随后安装 Comfy Remote、验证包可以从 `.venv` 正常 import，最后进入 Setup 向导。基础/全局 Python 只负责提供和创建项目环境，Panel 的正常运行仍优先使用 `.venv`。

Setup 完成后：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

如果 Setup 已配置 Tailscale Serve，手机打开向导显示的 `https://…ts.net` 地址。

### 更新

日常更新前确认没有重要任务正在运行，然后执行：

```powershell
git pull
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

Comfy Remote 使用 editable install，正常情况下 `git pull` 会直接更新现有 `.venv` 所引用的项目源码，重启 Panel 后即可加载新代码。只有在版本修改依赖或安装元数据、需要重新检查 Setup / 配置，或者 Python / `.venv` 环境需要修复时，才重新运行 `Install-ComfyRemote.ps1`。

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

## Known limitations — v0.4.6 Public Beta

- **Windows 10/11 是当前主要验证平台。** Linux 参与 CI，但公开安装和真机使用路径目前以 Windows 为主。
- **Tailscale 是当前主要远程传输方式。** 核心架构不要求永远绑定 Tailscale，但其他远程 transport 尚未形成同等级公开安装路径。
- **恢复仍是人工操作，不是完整 watchdog。** Panel 能识别已核验的受管/非受管 ComfyUI 进程状态并提供受控恢复，但不会自动处理 crash loop、GPU/驱动故障，也不会自动续跑或重新提交被中断任务。
- **真实硬卡死 / OOM 恢复继续依赖现场补充验证。** 安全保护路径有自动化覆盖，但 v0.4.6 不会为了发布验收故意制造 GPU / ComfyUI 卡死。
- **任务状态仍以证据为准。** 生成产物删除只决定历史记录是否继续保留，不会把成功任务改写成失败；也不会仅凭残留文件反推旧任务执行成功。
- **不提供 Ollama 管理层。** H3 FL2VA 高级设置只修改传给 `H3PromptStandardizer` 的模型名；Panel 不负责启动/关闭 Ollama、下载/删除模型或自动读取模型列表。
- **ComfyUI Qwen3.5 标准化依赖对应 H3 custom nodes 与本地 Qwen3.5 模型已经安装且能运行。** Panel 不自动下载这些模型资源。
- **没有 Wake-on-LAN。** 电脑睡眠、关机后的机外唤醒不属于 v0.4.6。
- **没有多主机。** 当前一个 Panel 对应本机一套 ComfyUI。
- **第三方 Custom Node 兼容性取决于 schema 和真实运行。** Configurator 2.0 会尽量分析，但不能保证所有第三方节点都能被自动理解。

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
- [Release Acceptance](docs/ACCEPTANCE.md)
- [Public Readiness Acceptance](docs/PUBLIC_READINESS_ACCEPTANCE.md)
- [TODO / Roadmap](docs/TODO.md)
- [Security](SECURITY.md)