# Windows ComfyUI Portable — Advanced Notes

普通用户优先使用 [Windows 从零开始教程](GETTING_STARTED_WINDOWS.md) 和 `Install-ComfyRemote.ps1`。本文只补充 Windows Portable 的高级/手动部署边界。

## 推荐：让 Setup 管理配置

```powershell
.\scripts\windows\Install-ComfyRemote.ps1
```

或已有 `.venv` 时：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe setup
```

Setup 可以接受 Portable bundle 根目录，也可以接受里面的 `ComfyUI` 子目录，并自动规范化：

```text
ComfyUI_windows_portable\
  python_embeded\python.exe
  ComfyUI\
    main.py
    input\
    output\
```

## Portable 启动脚本

如果允许 Comfy Remote 启动/关闭/重启 ComfyUI，Setup 会扫描 Portable 根目录中的 `.bat` 启动脚本。

对于静态、可安全解析的启动行，例如：

```text
python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --enable-manager
```

或：

```text
python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --enable-manager --use-sage-attention
```

Setup 会让用户在多个有效启动方式之间显式选择，并把真实 Python 参数写入 `[comfyui.control].start_command`。

Comfy Remote **不会因为检测到 SageAttention 已安装就自动决定使用它**；安装了某个优化库不代表用户希望每次启动都启用对应参数。

为避免 `cmd.exe → .bat → python.exe` 带来的 PID/进程树歧义，能够安全解析时会直接启动 Portable 的 `python.exe`，同时保留脚本中的静态参数。

复杂、依赖动态环境变量/额外 shell 逻辑的 `.bat` 不会被强行猜测。

## ComfyUI 控制台与 Panel 控制台

Windows 上默认行为：

- Comfy Remote Panel 自身后台运行，不留下额外黑色控制台窗口；
- 由 Panel 启动的 ComfyUI 默认保留自己的可见控制台窗口，便于观察加载与节点报错。

这是两个不同进程的显示策略。

## 手动配置 `config.toml`

Setup 是公开 happy path；手动 TOML 只用于高级排障或特殊部署。

可以从 `config.example.toml` 开始：

```powershell
Copy-Item config.example.toml config.toml
```

重点字段：

```toml
[comfyui]
base_url = "http://127.0.0.1:8188"
input_dir = "../ComfyUI/input"
output_dir = "../ComfyUI/output"

[comfyui.control]
enabled = true
working_dir = "../ComfyUI_windows_portable"
start_command = ["../ComfyUI_windows_portable/python_embeded/python.exe", "-s", "ComfyUI/main.py", "--windows-standalone-build", "--enable-manager"]
visible_window = true
```

根据你的真实目录和启动参数调整。不要把机器专用 `config.toml` 提交到 Git。

## 生命周期安全边界

Comfy Remote 的 stop/restart 不应按“看起来像 Python”或“碰巧占用端口”去杀进程。

Panel 会记录它启动的 ComfyUI 进程信息，并在停止前核验目标。身份无法可靠确认时，允许停止失败，也不应误杀其他 Python/浏览器/用户进程。

复杂故障和更强的 crash recovery 属于 v0.4 Reliability / Recovery 范围。

## Tailscale

公开支持路径仍是：

```text
Phone
→ Tailscale Serve HTTPS
→ 127.0.0.1:8190 Comfy Remote
→ 127.0.0.1:8188 ComfyUI
```

让 Setup 配置 Serve 最简单。手动检查：

```powershell
tailscale status
tailscale serve status
```

不要启用 Funnel，也不要把 8188/8190 直接做公网端口映射。

## Windows 登录自启动

优先使用 CLI：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart install
.\.venv\Scripts\comfyui-remote-panel.exe autostart status
.\.venv\Scripts\comfyui-remote-panel.exe autostart remove
```

当前实现会让 Windows 登录入口使用与手工 `comfyui-remote-panel start` 一致的后台启动语义；如果 Scheduled Task 注册因当前用户权限被拒绝，会尝试用户级 fallback。

旧 PowerShell task helper 仍保留给内部/高级调用，但普通用户不需要直接操作它们。
