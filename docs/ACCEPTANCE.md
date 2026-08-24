# v0.1.0 实机验收 / Release Acceptance

自动化测试不替代真实模型和手机网络验收。发布源码 Release 前完成并记录以下项目。

## 生成

- 使用 0.2 MP、5 秒分别提交纯文字、仅首帧、仅尾帧、首尾帧。
- 核对实际 Prompt 仍为 Euler、Beta、8 步、denoise 1、既定 LoRA/Sigma Shift、24 fps。
- 验证排队位置包含 ComfyUI 原界面任务；取消只影响目标 UUID。
- 验证失败摘要、原参数/图片/实际种子载入表单后再确认提交，以及高负载提示。
- 验证 Ref2VA 多参考图、参考视频（含配对音轨）、独立参考音频的上传、重试和删除。

## 恢复与文件

- 在 submitting、queued、running 阶段分别重启面板，核对队列/历史恢复。
- 手机切到后台再返回，确认 SSE 新快照恢复任务和指标。
- 验证 MP4 拖动播放、Range 下载和文件名。
- 删除终态任务，确认只删除数据库登记的专用目录文件；部分删除失败时记录仍保留。

## 设备与网络

- 将 GPU、显存、温度、功耗与 `nvidia-smi` 交叉核对，将内存与 Windows 任务管理器交叉核对。
- 确认面板监听地址仅为 `127.0.0.1:8190`，ComfyUI 仅为本机 `8188`。
- 从局域网地址直接访问 8190 应失败；缺失或错误身份头应返回 403。
- 从手机经 Tailscale HTTPS 完成上传、生成、后台恢复、播放和下载。
- 确认未启用 Funnel 或端口映射，原工作流、已有输出和 H3 Ledger 未受影响。

CI release gates remain: Windows/Linux, Python 3.11/3.13, tests, source build, and repository secret/media scan.
