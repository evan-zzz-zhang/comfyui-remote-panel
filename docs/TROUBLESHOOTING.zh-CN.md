# Troubleshooting

[English](TROUBLESHOOTING.md) | **简体中文**

排障第一步统一运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

需要反馈时再运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

## 项目 `.venv` / Python 环境损坏

如果 `.\.venv\Scripts\python.exe` 无法正常启动、基础标准库 import 失败，或者出现 `SRE module mismatch` 一类错误，不要尝试手工修补 `site-packages`，也不要把 Panel 长期改成用全局 Python 运行。

在项目根目录重新运行 Windows 安装器：

```powershell
.\scripts\windows\Install-ComfyRemote.ps1
```

从 v0.4.4 开始，安装器会真正启动已有 `.venv`，检查基础 Python 模块和 `pip`。健康环境直接复用；损坏环境会先保留为 `.venv.broken-YYYYMMDD-HHMMSS`，然后用健康的稳定版基础 Python 创建新的 `.venv`，再次健康检查并重新安装 Comfy Remote。

这个安装器路径用于首次安装、依赖/安装元数据变化、需要刷新 Setup / 配置，以及环境修复。正常代码更新仍然只需要：

```powershell
git pull
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

## setup 找不到 ComfyUI

确认你输入的是以下两种根目录之一：

```text
ComfyUI_windows_portable\
  python_embeded\
  ComfyUI\
    main.py
```

或：

```text
ComfyUI\
  main.py
```

向导不会全盘扫描。可以直接手动输入根目录；也可以设置环境变量 `COMFYUI_ROOT` 后重新运行 setup。

## 8188 连不上

先在电脑浏览器打开 `http://127.0.0.1:8188`。如果打不开，先解决 ComfyUI 本身的启动问题。Comfy Remote 不负责替代 ComfyUI 的基础安装。

## 8190 被占用

运行：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe status
```

如果显示 `port-occupied`，Panel 不会强杀未知进程。先确认占用 8190 的程序并关闭它，再启动 Comfy Remote。

## 浏览器返回 403

Tailscale auth 模式下，直接访问 `http://127.0.0.1:8190` 除 `/healthz` 外返回 403 是预期行为，因为请求没有 Tailscale Serve 注入的身份头。

请从 `tailscale serve status` 显示的 HTTPS 地址访问。若只需本机调试，可重新运行 setup 并使用 local auth。

## Tailscale 未登录

检查：

```powershell
tailscale status
```

确保电脑与手机登录同一个 tailnet。完成登录后重新运行 setup。

## Serve 地址打不开

检查：

```powershell
tailscale serve status
tailscale status
.\.venv\Scripts\comfyui-remote-panel.exe status
```

三层必须同时成立：Panel 在 127.0.0.1:8190 健康运行、Tailscale backend 已连接、Serve 指向 8190。需要重新配置时运行 `tailscale serve --bg 8190`。

## 手机打不开但电脑能打开

确认手机 Tailscale 已连接、与电脑在同一 tailnet、使用 `https://...ts.net` Serve 地址，而不是局域网 IP，并检查 `doctor` 中 `allowed login` 是否身份不匹配。

## Workflow 缺节点

工作流导入/验证会根据当前 ComfyUI `object_info` 判断 `class_type` 是否存在。安装对应 custom node、重启 ComfyUI、重新运行 `doctor`，然后重新测试。

不要因为一个内置 H3 工作流缺节点就判断 Panel 安装失败；内置 H3 是可选验证示例，缺依赖只应是 `WARN`。

## Workflow 缺模型

节点存在但模型清单找不到时，工作流会显示不可用/缺依赖。把模型放到该节点实际读取的 ComfyUI 模型目录，确认 ComfyUI 自己能加载，再重新测试。

## 导入成功但测试失败

“导入成功”只证明 JSON、节点结构和映射可解析；真实测试还会暴露模型缺失、路径错误、显存不足、自定义节点运行时异常或输出节点未写出预期 artifact。

查看任务错误摘要与 ComfyUI 控制台，并附 `doctor --report` 提交兼容性 Issue。

## 图片上传失败

确认文件格式正确、ComfyUI `input` 目录可写、`doctor` 的 input directory 为 `PASS`，并保证磁盘有足够空间。

## 生成后结果找不到

确认 ComfyUI 任务本身完成、工作流已选择正确的 SaveImage/SaveVideo/输出节点、`output` 目录可读，且生成时没有手动移动/清理文件。自定义工作流若有多个输出候选，导入时要确认主要输出。

## 任务运行时重启了 Panel

重启 Comfy Remote 不会主动取消已经被 ComfyUI 接受的 prompt。Panel 重启后会根据 ComfyUI 的 queue/history 重新确认未完成任务状态。v0.4.3 不再把尚未最终写完的 history 记录直接当成失败；即使最终 history payload 还没落盘，明确的 `execution_success` 也会被视为成功证据。

如果某条任务已经被旧版本误判，并且 ComfyUI 后续又清掉了这条任务的 history，v0.4.3 不会仅凭残留 MP4 文件名反推任务成功。视频文件可能仍在受管输出目录，但任务状态仍以明确的 ComfyUI 证据为准。

## Panel 重启后打不开

运行 `status` 和 `doctor`。后台启动失败时查看：

```text
data\panel-launch.log
data\panel.log
```

不要手工删除陌生 Python 进程；`stop` 会在停止前核验进程身份。

## Windows 登录后没有自动启动

检查：

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart status
```

必要时重新执行 `autostart remove` 和 `autostart install`，然后真正做一次 Windows 注销/登录验收。

## H3 全部不可用

这不影响普通 ComfyUI API Workflow。H3 工作流依赖 MiniMax H3 对应 custom node、模型/VAE/文本编码器等环境。公开版本把它们视为 Bundled / Verified examples，而不是 Comfy Remote 核心安装前提。
