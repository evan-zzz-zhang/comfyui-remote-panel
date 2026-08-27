# Windows 从零开始：第一次使用 Comfy Remote

本文档面向**第一次接触 Comfy Remote** 的 Windows 用户。假设你会正常使用 ComfyUI，但不要求你熟悉 Python 项目、TOML、Task Scheduler、节点 ID 或 Tailscale Serve。

目标不是“把程序装上”，而是完整走通：

```text
准备电脑
→ 安装 Comfy Remote
→ Setup
→ Doctor
→ 手机打开面板
→ 导入自己的 API Workflow
→ Preflight / Test
→ 第一次真实生成
→ 在手机查看结果
```

> **v0.3.0 是 Public Beta。** Windows 10/11 是当前主要验证平台，Tailscale 是当前主要远程访问方式。

---

## 1. 开始前确认 ComfyUI 本身正常

先不要安装 Comfy Remote。

在这台 Windows 电脑上启动你平时使用的 ComfyUI，并确认至少一个工作流能够在本机正常生成。

Comfy Remote 不负责安装 ComfyUI、模型或第三方 Custom Node。它是在“本机 ComfyUI 已经可用”的基础上提供远程控制和手机创作界面。

**不要求 MiniMax H3。** 内置六个 H3 工作流只是 Bundled / Verified examples。如果你不用 H3，之后看到它们不可用或 Doctor 出现 H3 `WARN` 可以直接忽略。

---

## 2. 准备 Git、Python 和 Tailscale

### Git for Windows

如果电脑没有 Git，安装官方 Git for Windows：

<https://git-scm.com/download/win>

安装完成后重新打开 PowerShell，检查：

```powershell
git --version
```

能看到版本号即可。

### Python

安装 **稳定版 Python 3.11 或更高版本**：

<https://www.python.org/downloads/windows/>

不要使用 `alpha`、`beta`、`rc` 等预发行 Python 作为 Comfy Remote 的公开安装环境。安装 Python 时建议勾选将 Python 加入 PATH（安装器中的 wording 可能是 `Add python.exe to PATH`）。

重新打开 PowerShell，检查：

```powershell
python --version
```

例如：

```text
Python 3.13.x
```

如果 `python` 打开 Microsoft Store、提示找不到命令，或者显示类似 `3.14.0a1` 的预发行版本，先修正 Python 安装再继续。

### Tailscale（只有手机远程使用才需要）

下载：

<https://tailscale.com/download>

电脑和手机都安装 Tailscale，并登录**同一个 tailnet**。电脑端可以用：

```powershell
tailscale status
```

确认已连接。

如果你暂时只想在电脑本机试用，可以不安装 Tailscale；Setup 会使用 local 模式完成配置。

---

## 3. 下载并安装 Comfy Remote

在 PowerShell 中进入你希望保存项目的目录，例如某个 AI 项目文件夹，然后运行：

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
.\scripts\windows\Install-ComfyRemote.ps1
```

安装器会：

```text
检查稳定版 Python
→ 创建项目自己的 .venv
→ 安装 Comfy Remote
→ 自动进入 Setup 向导
```

它不会修改 ComfyUI 核心代码。

### PowerShell 阻止脚本怎么办

如果出现 Execution Policy 相关错误，可以只对**当前 PowerShell 进程**临时放宽：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

然后重新执行：

```powershell
.\scripts\windows\Install-ComfyRemote.ps1
```

---

## 4. Setup：每个问题应该怎么选

首次安装时 Setup 会尽量自动判断，只有真正存在选择时才询问。

### 4.1 ComfyUI 在哪里

如果只找到一套 ComfyUI，会直接使用，不再确认。

如果找到多套，会出现类似：

```text
发现多个可能的 ComfyUI：
  [1] ...
  [2] ...
  [0] 手动输入
选择 ComfyUI:
```

选择你实际要远程控制的那一套。

如果自动找不到，会要求输入 ComfyUI 根目录。Windows Portable 可以输入：

```text
D:\你的目录\ComfyUI_windows_portable
```

也可以输入里面的：

```text
D:\你的目录\ComfyUI_windows_portable\ComfyUI
```

Setup 会自动规范化到 Portable 根目录。

### 4.2 是否允许 Comfy Remote 控制 ComfyUI

会看到：

```text
允许 Comfy Remote 启动、关闭和重启 ComfyUI [y/N]:
```

- 如果希望以后在手机“设备”页启动 / 关闭 / 重启 ComfyUI：输入 `y`。
- 如果你始终自己在电脑上启动 ComfyUI：直接回车即可保持关闭。

这是功能权限选择，不影响导入和远程提交工作流。

### 4.3 选择 ComfyUI 启动方式

只有你允许生命周期控制，并且 Portable 根目录检测到多个有效启动脚本时才会出现。

例如：

```text
检测到多个 ComfyUI 启动脚本：
  [1] 启动ComfyUI.bat
      -s ComfyUI/main.py --windows-standalone-build --enable-manager
  [2] 启动ComfyUI_SageAttention.bat
      -s ComfyUI/main.py --windows-standalone-build --enable-manager --use-sage-attention
  [0] 使用 Comfy Remote 默认启动命令
选择启动方式:
```

**选择你平时实际使用的启动方式。**

Comfy Remote 会提取脚本里的静态 Python 启动参数并直接启动 Python，不会为了方便自行删掉 `--enable-manager`、`--use-sage-attention` 等真实参数。

Windows 上由 Comfy Remote 启动 ComfyUI 时，默认保留 ComfyUI 自己的控制台窗口，方便观察加载和报错；Panel 自身不会留下额外黑色控制台窗口。

### 4.4 Tailscale

如果电脑已经登录 Tailscale，会显示当前身份，然后询问：

```text
启用 Tailscale 远程访问 [Y/n]:
```

想从手机访问就直接回车或输入 `y`。

Setup 会自动配置 Tailscale Serve，并显示类似：

```text
远程地址: https://...ts.net
```

**把这个地址留着，稍后手机打开。**

不要启用 Tailscale Funnel，也不要把 Panel 8190 或 ComfyUI 8188 做公网端口映射。

### 4.5 Windows 登录自启动

首次配置会询问：

```text
Windows 登录后自动启动 Comfy Remote [Y/n]:
```

推荐保持 `Y`。这样 Windows 登录后 Panel 会自动恢复，你不需要每次手工执行 `start`。

以后重新运行“检查并更新”时，如果已经配置过自启动，Setup 会自动保留/刷新，不再重复问。

### 已经有 config.toml 时

重新运行 Setup 会看到：

```text
  [1] 检查并更新
  [2] 创建新配置（自动备份旧文件）
  [3] 退出
选择操作:
```

这里没有隐藏默认选项，直接输入 `1`、`2` 或 `3`。

---

## 5. 先运行 Doctor

Setup 完成后：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

重点看：

```text
Core
ComfyUI
Remote access
Workflow compatibility
Overall
```

核心依赖正常时应为 `PASS`。

`WARN` 不一定代表安装失败。例如：

- 没装 / 没登录 Tailscale；
- 你不用的内置 H3 工作流缺模型；
- 某个可选工作流缺 Custom Node。

真正需要先处理的是关键 `FAIL`，例如 ComfyUI API 不通、input 不可写等。

需要反馈问题时：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

它会输出适合 Issue 的脱敏 Markdown。**公开发送前仍请自己浏览一遍，不要上传配置、数据库、完整日志或真实素材。**

---

## 6. 启动 Panel

如果 Setup 的 Windows 自启动已经让 Panel 运行，`start` 会安全地识别已运行实例。

运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

正常状态类似：

```text
Panel      Running
PID        12345
Port       8190
Health     OK
```

停止 / 重启：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe stop
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

---

## 7. 第一次打开 Comfy Remote

### 手机远程

手机确认 Tailscale 已连接同一个 tailnet，然后在浏览器打开 Setup 给出的：

```text
https://...ts.net
```

电脑端如果忘记地址，可以检查：

```powershell
tailscale serve status
```

### 只在电脑本机测试

如果 Setup 使用 local auth，可以在电脑浏览器打开：

```text
http://127.0.0.1:8190
```

如果配置的是 Tailscale auth，直接访问 localhost 除健康检查外返回 403 属于预期行为，请使用 Tailscale Serve HTTPS 地址。

---

## 8. 最关键的一步：导出正确的 ComfyUI API Workflow

Comfy Remote 需要的是 **API Workflow JSON**，不是普通“保存工作流”得到的 UI Workflow JSON。

先回到 ComfyUI：

1. 打开并运行你准备远程使用的工作流，确认它在本机成功生成。
2. 如果界面里看不到 API 格式导出选项，进入 ComfyUI Settings，开启 **Dev Mode / Developer Mode Options**（不同前端版本 wording 可能略有不同）。
3. 使用 **Save (API Format)**、**Export (API)** 或当前版本中等价的 API 格式导出入口。
4. 保存得到的 `.json` 文件。

简单判断：API Workflow 通常以节点 ID 为 key，每个节点包含 `class_type` 和 `inputs`；它不是包含画布位置、颜色、widget UI 状态为主的普通 Workflow 文件。

如果上传后 Comfy Remote 明确提示不是 API Workflow，不要手工改 JSON，回到 ComfyUI 重新使用 API 格式导出。

---

## 9. 在 Comfy Remote 导入自己的 Workflow

进入：

```text
设置
→ 工作流
→ 导入工作流
```

然后：

1. 选择刚导出的 API Workflow JSON。
2. 查看 Configurator 2.0 自动分析结果。
3. 检查识别出的提示词、媒体输入、参数和主要输出。
4. 如果出现多个候选或低置信度项，按你的真实工作流含义选择。
5. 必要时使用“高级 · 手动节点映射”补充自动分析无法可靠判断的字面输入。
6. 保存并启用。
7. 执行一次“测试”。

测试会**真实提交 ComfyUI 任务并使用 GPU**，不是只做 JSON 校验。

### Configurator 2.0 不要求固定参数

不要因为导入页面没有 `width` / `height` / `batch_size` 就认为识别失败。

不同工作流能力不同。例如 img2img 可能继承输入图片尺寸；某些视频工作流把尺寸封装在 custom node 中；有些工作流根本不允许远程修改 batch。

Comfy Remote 使用：

```text
Schema
+ Graph connections
+ conservative heuristic fallback
+ explicit user mapping
```

来决定应该暴露什么，而不是强迫所有工作流长成同一种结构。

---

## 10. 第一次真实生成

回到：

```text
创作
```

选择刚启用的工作流。

根据它真实声明的能力：

- 填提示词；
- 上传需要的图片 / 视频 / 音频；
- 调整允许远程修改的参数；
- 提交任务。

随后进入任务页，正常链路是：

```text
提交
→ 排队
→ 生成
→ 完成
→ 查看 / 下载结果
```

如果失败：

1. 先看任务错误摘要；
2. 看 ComfyUI 自己的控制台；
3. 运行 `doctor`；
4. 再查 [Troubleshooting](TROUBLESHOOTING.md)。

---

## 11. 什么叫“第一次安装成功”

完成以下项目就算真正走通，而不仅仅是“服务启动了”：

- [ ] `doctor` 没有阻塞使用的核心 `FAIL`。
- [ ] 手机能通过 Tailscale HTTPS 打开 Comfy Remote（或本机 local 模式能打开）。
- [ ] 成功导入一个**你自己的** API Workflow。
- [ ] Preflight 没有未处理的阻塞 `FAIL`。
- [ ] Runtime Test 成功，或明确知道失败来自工作流自己的模型/节点环境。
- [ ] 创作页能正常填写该工作流需要的输入。
- [ ] 一次真实任务完成。
- [ ] 手机任务页能看到并打开生成结果。

**如果你不用 H3，六个内置 H3 工作流是否可用不属于这个成功标准。**

---

## 12. Windows 登录自启动

查看状态：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart status
```

手动安装 / 移除：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart install
.\.venv\Scripts\comfyui-remote-panel.exe autostart remove
```

---

## 13. 更新项目

Public Beta 阶段更新较快。更新前建议没有正在运行的重要任务，然后：

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\comfyui-remote-panel.exe setup
.\.venv\Scripts\comfyui-remote-panel.exe doctor
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

Setup 的“检查并更新”会尽量保留有效配置，并在改写前备份 `config.toml.bak`。

---

## 下一步

- 工作流识别与 Configurator 2.0：[WORKFLOWS.md](WORKFLOWS.md)
- 常见问题：[TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 安全边界：[../SECURITY.md](../SECURITY.md)
- 当前路线图：[TODO.md](TODO.md)
