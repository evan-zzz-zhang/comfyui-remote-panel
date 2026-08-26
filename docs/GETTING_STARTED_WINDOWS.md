# Windows 快速开始

本文档面向一台**从未安装过 Comfy Remote** 的 Windows 电脑。唯一前提是：这台电脑上的 ComfyUI 已经能在本机正常完成一次生成。

## 1. 准备

需要：

- Windows 10/11。
- Python 3.11 或更高版本。
- 一个本机可用的 ComfyUI。
- 若要从手机远程访问：电脑和手机安装 Tailscale，并登录同一个 tailnet。

Comfy Remote 不要求安装 MiniMax H3。内置 H3 工作流只是验证示例；没有对应节点或模型时，它们会显示为不可用，但不会阻止 Panel 启动或导入自己的工作流。

## 2. 安装

在 PowerShell 中进入希望保存项目的位置：

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
.\scripts\windows\Install-ComfyRemote.ps1
```

脚本只做三件事：检查 Python、创建 `.venv` 并安装项目，然后进入 Python 的 `setup` 向导。核心配置逻辑不写在 PowerShell 中。

如果 PowerShell 阻止本地脚本，可只为当前进程放宽策略后重试：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

## 3. Setup 会做什么

运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe setup
```

向导会：

1. 检查 Python、当前目录与既有 `config.toml`。
2. 优先探测 `http://127.0.0.1:8188` 是否已有 ComfyUI 在线。
3. 在少量常见位置寻找 ComfyUI；找不到时让你手动输入根目录。
4. 验证 `main.py`、`input`、`output`，并生成配置。
5. 单独询问是否允许 Panel 启动/关闭/重启 ComfyUI。默认关闭。
6. 检测 Tailscale 登录身份；可用时询问是否配置 `tailscale serve --bg 8190`。
7. Windows 上询问是否安装登录后自动启动。默认开启。

检测到旧配置时不会直接覆盖；“检查并更新”会沿用有效设置，写入前会备份旧配置为 `config.toml.bak`。

## 4. 诊断

Setup 完成后先运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

预期核心项目应为 `PASS`。Tailscale 未安装、内置 H3 缺依赖等可选能力会显示 `WARN`。

需要提交兼容性问题时：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

该输出适合直接粘贴到 GitHub Issue；用户目录、邮箱、Tailscale 主机名和明显 secret 值会自动脱敏。

## 5. 启动 Panel

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

状态示例：

```text
Panel      Running
PID        12345
Port       8190
Health     OK
```

停止或重启：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe stop
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

旧用法仍兼容：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe --config config.toml
```

这会以前台方式运行服务。

## 6. 手机远程访问

如果 setup 已配置 Tailscale Serve，在电脑上确认：

```powershell
tailscale serve status
```

手机连接同一个 tailnet 后，打开 setup 输出的 `https://<device>.<tailnet>.ts.net` 地址。

不要使用 Tailscale Funnel，也不要把 8190 或 ComfyUI 8188 直接端口映射到公网。

如果当前只想本机测试，setup 可以在 `local` auth 模式下完成。此时浏览器访问：

```text
http://127.0.0.1:8190
```

## 7. 导出自己的 ComfyUI API Workflow

先在 ComfyUI 中确认工作流能正常运行，然后使用 **API 格式导出**。不要上传普通 UI workflow、网页内容或日志文件。

在 Comfy Remote：

1. 打开“设置 → 工作流”。
2. 选择“导入工作流”。
3. 上传 API Workflow JSON。
4. 检查自动识别的提示词、参考素材、尺寸/批次和输出。
5. 若有多个候选，在导入页确认正确映射。
6. 保存并启用。
7. 先执行一次“测试”。测试会真实提交 ComfyUI 任务并使用 GPU。

兼容性检查分四层理解：

- **JSON**：必须是可解析的 API Workflow。
- **Node**：工作流使用的 `class_type` 必须存在于当前 ComfyUI `object_info`。
- **Input/Output**：尽量识别 prompt、negative、image/video、width、height、batch 与主要输出；复杂参数可手动映射。
- **Runtime**：模型文件、路径、显存和真实节点行为只能由实际测试最终证明。

## 8. 第一次生成

回到“创作”页，选择刚导入的工作流，填写提示词/素材并提交。

随后在“任务”页确认：

```text
提交 → 排队 → 生成 → 完成 → 查看/下载
```

如果生成失败，先运行 `doctor`，再看任务错误摘要和 ComfyUI 控制台。

## 9. 登录后自动启动

查看：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart status
```

手动安装或移除：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart install
.\.venv\Scripts\comfyui-remote-panel.exe autostart remove
```

发布验收不能只看“任务创建成功”。必须在真实 Windows 上执行一次“注销 → 登录 → 手机重新访问”。

## 下一步

遇到问题先看 [Troubleshooting](TROUBLESHOOTING.md)。提交工作流兼容性问题时优先附上 `doctor --report`。
