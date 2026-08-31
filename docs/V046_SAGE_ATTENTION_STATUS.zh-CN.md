# v0.4.6 SageAttention 运行状态

设备页可以显示当前实际运行的 ComfyUI 是否使用了 `--use-sage-attention` 启动参数。

## 设备概览

默认情况下，现有设备概览保持不变：

- Panel
- ComfyUI
- 队列任务

当当前配置的 ComfyUI 端口上，实际运行且已安全识别的 ComfyUI 监听进程命令行包含 `--use-sage-attention` 时，会在“队列任务”右侧追加第 4 个 `SageAttention` 状态框。没有该参数时不显示额外状态框，仍保持原来的三个状态框。

## 判定来源

状态不会根据 `config.toml` 猜测。配置中的启动命令和当前实际运行进程可能不同，例如 ComfyUI 被其他本地工具手动重启时。

因此 Comfy Remote 会检查当前安全识别出的 ComfyUI 监听进程，并读取该进程的实际命令行。若无法安全识别监听进程，则不显示 SageAttention 状态框。

这个状态仅用于显示，不会修改 ComfyUI 启动参数、工作流或 Attention 行为。
