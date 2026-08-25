# ComfyUI Remote Panel

一个面向手机、只运行受信任预设的轻量 ComfyUI 控制面板。当前版本提供六个经审核的 MiniMax H3 FL2VA/Ref2VA 预设，不代理完整 ComfyUI，也不接受任意工作流。

## 特性

- 纯文字、首帧、尾帧和首尾帧四种模式
- 八种固定画幅，以及按参考图自动取比例（首尾帧都有时优先首帧）
- 多任务 FIFO、实时阶段/采样进度、定向取消，以及先载入表单再确认提交的原参数重试
- 高级区可切换六个工作流，并调整其声明允许的调度器、采样器和迭代步数
- Ref2VA 支持最多 9 张参考图、3 段参考视频和 3 段独立参考音频；视频画面及内嵌音轨会自动连接到配对端口
- SQLite 历史、MP4 Range 播放/下载和安全的手动删除
- NVIDIA GPU、显存、温度、功耗、内存和 ComfyUI 状态
- 设备页按固定本机配置远程启动、关闭和重启 ComfyUI
- Tailscale Serve 身份头认证；除 `/healthz` 外没有匿名入口
- 原生 HTML/CSS/JS，无 Node.js 和前端构建步骤

## 要求

- Python 3.11 或更高版本
- ComfyUI 0.26.0 或更高版本，面板与 ComfyUI 位于同一台机器
- MiniMax H3 预设清单中列出的模型和 LoRA
- Tailscale Serve；不要使用 Funnel，也不要把面板或 8188 暴露到公网

## 安装

```text
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[test]"
```

复制 `config.example.toml` 为不受 Git 跟踪的 `config.toml`，填写 ComfyUI 输入/输出目录、Tailscale HTTPS Origin 和唯一允许的登录身份。所有相对路径都以配置文件所在目录为基准。

```text
.venv/Scripts/comfyui-remote-panel --config config.toml
tailscale serve --bg 8190
```

访问 `tailscale serve status` 显示的 HTTPS 地址。直接访问本机 8190 不会带身份头，因此除健康检查外会返回 403，这是预期行为。

Windows Portable 的逐步部署、身份确认和启动器集成见 [docs/WINDOWS_PORTABLE.md](docs/WINDOWS_PORTABLE.md)。发布前实机检查见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)。

## 配置与数据

- 面板强制监听 `127.0.0.1`。
- 上传保存到 ComfyUI 输入目录下的单层 `h3_remote/` 平铺目录，文件名带有任务短标识。
- 视频保存到 ComfyUI 输出目录下的单层 `h3_remote/` 平铺目录，完成后统一收敛为 `*_result.mp4`。
- “移出历史”默认只隐藏数据库任务并保留本地产物；物理清理必须调用显式 purge 接口。
- 数据库位于配置的 `data_dir`；旧版 UUID 子目录会在启动时迁移到平铺目录，未登记文件只告警不自动删除。
- 面板启动不依赖 ComfyUI 在线；预设会在后台通过 ComfyUI 节点和模型接口检查，服务离线时页面保持可用，生成按钮禁用。
- 设备控制默认关闭；启用 `[comfyui.control]` 后，面板只执行本机固定命令，并在关闭前核验监听进程身份。

## 开发与测试

```text
.venv/Scripts/python -m pytest
.venv/Scripts/python scripts/check_repository.py
```

Windows/Linux 与 Python 3.11/3.13 会在 GitHub Actions 中执行同样的检查。实机 GPU 生成不属于 CI；发布前按文档中的四种输入模式逐一验收。

## English

ComfyUI Remote Panel is a mobile-first, local companion for reviewed ComfyUI workflow presets. The current version ships six MiniMax H3 FL2VA/Ref2VA presets and deliberately does not expose arbitrary prompt graphs or the full ComfyUI interface.

The H3 preset supports eight fixed aspect ratios plus a reference-image ratio. It uses the first frame when present and otherwise falls back to the last frame.

It requires Python 3.11+, ComfyUI 0.26.0+, and same-host filesystem access. Tailscale Serve remains the recommended/default access provider: copy `config.example.toml`, install the package in a virtual environment, start the panel, and run `tailscale serve --bg 8190`. Set `auth.provider = "local"` only for loopback-only local use; this mode refuses non-loopback origins and clients. Every route except the minimal health endpoint passes through the selected authentication provider.

See [SECURITY.md](SECURITY.md) before deployment. Models, LoRAs, user uploads, generated videos, databases, logs, identities, and machine-specific configuration are never distributed with this repository.

For a detailed Windows Portable setup and launcher integration, see [docs/WINDOWS_PORTABLE.md](docs/WINDOWS_PORTABLE.md). The release acceptance checklist is in [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).
