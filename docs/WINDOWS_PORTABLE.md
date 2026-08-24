# Windows ComfyUI Portable 部署 / Deployment

## 中文

1. 安装 Python 3.11 或更高版本，在仓库根目录执行：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e .
   Copy-Item config.example.toml config.toml
   ```

2. 编辑不受 Git 跟踪的 `config.toml`。Portable 默认输入和输出通常位于发行目录内的 `ComfyUI\input` 与 `ComfyUI\output`；使用相对配置时，路径以 `config.toml` 所在目录为准。`allowed_logins` 必须填写 `tailscale status --json` 中当前用户的 `LoginName`，`public_origin` 必须是 Serve 显示的完整 HTTPS Origin。

   若要使用设备页的启动、关闭和重启按钮，配置 `[comfyui.control]`：将 `enabled` 设为 `true`，`working_dir` 指向 Portable 根目录，`start_command` 使用参数数组。面板不通过 shell 执行这条命令；关闭时只会停止监听 ComfyUI 端口、且可核验为相同可执行文件与参数的进程。Windows 下将 `visible_window` 设为 `true` 会为新启动的 ComfyUI 打开可见控制台并在其中显示输出；设为 `false` 时输出写入 `data/comfyui-control.log`。

3. 确认 Manifest 中的五个模型依赖已安装。模型名称和目录必须与 `workflows/h3-fl2va-v4step600/manifest.json` 完全一致。仓库不分发模型或 LoRA。

4. 启动面板并检查健康状态：

   ```powershell
   .\.venv\Scripts\python.exe -m comfyui_remote_panel --config config.toml
   Invoke-RestMethod http://127.0.0.1:8190/healthz
   ```

5. 安装 Tailscale，在电脑和手机上登录同一 tailnet。只配置 Serve，不启用 Funnel：

   ```powershell
   tailscale serve --bg 8190
   tailscale serve status
   ```

6. 浏览器经 Serve HTTPS 地址访问。直接访问 `http://127.0.0.1:8190/` 返回 403 是预期行为；`8188` 与 `8190` 都不得做路由器端口映射。

仓库的 `scripts/windows/Start-RemotePanel.ps1` 是独立示例，只启动面板并等待健康检查。若集成进自定义 ComfyUI 启动器，应只识别专用虚拟环境与 `-m comfyui_remote_panel` 命令行，记录本次新建的 PID，并在 ComfyUI 退出时只停止该 PID。启动器不应管理 Tailscale Serve。

## English

Create a Python 3.11+ virtual environment, install the project, and copy `config.example.toml` to the ignored `config.toml`. Point the input/output settings at the same-host ComfyUI folders. Set `allowed_logins` to the signed-in Tailscale user's exact `LoginName` and set `public_origin` to the HTTPS origin printed by Tailscale Serve.

Install every model named in the preset manifest, start the panel, verify `/healthz`, then run `tailscale serve --bg 8190`. Install Tailscale on the phone and join the same tailnet. Never enable Funnel, router port forwarding, or external listening for either port 8188 or 8190.

The sample PowerShell script starts only the panel. A local launcher integration must reuse matching processes and terminate only processes it created during that launch.

To enable the device-page controls, configure `[comfyui.control]` as shown in `config.example.toml`. The configured command is executed directly without a shell. Stop and restart only target the process listening on the configured ComfyUI port after its executable and command arguments have been verified. On Windows, `visible_window = true` opens a console for newly started ComfyUI processes; in hidden mode, output is written to `data/comfyui-control.log`.
