# Comfy Remote TODO

本文档是 Comfy Remote 的执行型 TODO。v0.2 已于 2026-08-26 完成实机验收；较早的架构诊断与历史问题仍保留在 `PROJECT_DIAGNOSIS_AND_TODO.md`。

## v0.2 — 已完成

- [x] 产品显示名称统一为 **Comfy Remote**。
- [x] 主导航统一为 **创作 / 任务 / 设备**。
- [x] 工作流管理移入设置，创作页一级选择工作流。
- [x] 工作流显示 / 隐藏即时响应并持久化。
- [x] FL2VA / Ref2VA / Generic 图片工作流采用统一创作结构。
- [x] H3 固定画幅收敛为 `9:16 / 16:9 / 1:1 / 3:4 / 4:3 / 21:9`，参考图 / 参考视频作为条件型画幅并置于末尾。
- [x] 删除创作、任务、设备页重复大标题和冗余说明文案。
- [x] 点击“任务”标签刷新任务，不再保留独立刷新按钮。
- [x] 任务卡不常驻显示 Prompt；任务详情保留唯一一份完整 Prompt 并提供轻量复制。
- [x] 图片 / 视频工作流统一“生成设置 → 高级设置”顺序。
- [x] 工作流“全部 / 视频 / 图片”筛选真实生效。
- [x] 自定义工作流导入、自动识别、编辑、测试、复制、导出、删除通过验收；删除即时生效，无需重启。
- [x] 建立 `UI_VISUAL_SPEC.md` 作为视觉与交互规范。
- [x] FL2VA / Ref2VA / 自定义图片工作流真实生成、结果查看与下载通过验收。
- [x] 提交、排队、进度、完成、取消、失败和基础“再次生成”链路通过验收。
- [x] 移动端 UI 与工作流导入管理由用户实机验收通过。
- [x] minimum-dependencies + Windows/Linux + Python 3.11/3.13 CI 全绿。

## Next — 生成现场恢复（Generation Reconstruction）

目标：让“再次生成”真正恢复原任务现场，而不只恢复数值和 retained 引用。

- [ ] Retry draft 明确返回并标识保留的输入素材。
- [ ] FL2VA 再次生成时恢复首帧 / 尾帧可视状态。
- [ ] 原首帧 / 尾帧仍存在时显示真实图片缩略图 + “沿用”。
- [ ] Ref2VA 恢复 Picture / Video / Audio 的原顺序和 retained 状态。
- [ ] 图片素材恢复缩略图。
- [ ] 视频 / 音频第一版允许使用文件卡，不强依赖媒体缩略图。
- [ ] 每个保留素材支持替换和删除。
- [ ] 原输入文件缺失时明确显示“原素材已丢失”。
- [ ] Generic 图片工作流恢复 positive / negative prompt、width / height、batch 和参考素材。
- [ ] 再次生成不因工作流在创作页被隐藏而失效。
- [ ] 为 retained media / retry reconstruction 增加 API 与回归测试。

## Next — 视频缩略图稳定性专项

目标：确认任务卡视频预览偶发黑屏、缩略图丢失或无法加载的真实原因，不用 UI 重试掩盖链路问题。

- [ ] 记录失败样本的浏览器、视频编码、文件大小和任务状态。
- [ ] 检查 MP4 是否有可快速读取的首帧 / metadata。
- [ ] 检查 Range 请求与浏览器首帧读取行为。
- [ ] 检查任务进入 succeeded 与文件实际稳定可读之间是否存在时序窗口。
- [ ] 检查不同 H3 输出编码 / 容器行为。
- [ ] 确定是否需要服务端生成稳定 poster / thumbnail。
- [ ] UI 增加明确的 thumbnail loading / unavailable 状态，但不无限反复 `load()`。

## Later — 高清参考图自动压缩

目标：避免超高分辨率参考图进入图像编码 / VAE 等节点后造成不必要显存压力。

正式开发前先确定：

- [ ] 压缩发生在浏览器端还是 Remote Panel 端。
- [ ] 使用“最大长边”还是“最大像素面积”作为限制。
- [ ] JPEG / PNG / WebP 输出格式策略。
- [ ] 是否保留原图，还是只保留生成用压缩副本。
- [ ] 是否默认开启，以及默认阈值。
- [ ] 不同工作流能否覆盖全局规则。
- [ ] EXIF / alpha / 色彩空间处理。
- [ ] 上传前是否显示压缩后的尺寸和预计大小。

建议最终进入：**设置 → 输入 / 素材 → 高清参考图自动压缩**。

## Later — 设置、连接与诊断完善

- [ ] 连接页显示当前 AuthProvider / 访问方式和可诊断状态。
- [ ] 日志与诊断页提供最近 Panel 日志、ComfyUI 可达性和常见故障摘要。
- [ ] 关于页显示版本、commit / build 信息和文档入口。
- [ ] 对尚未实现的设置能力提供明确状态，避免“看似可点但无反馈”。

## Later — Windows 工作站生命周期

这些能力应进入 **设备 / 工作站**，而不是常规设置。

- [ ] Windows 睡眠。
- [ ] Windows 休眠（如果目标机器启用）。
- [ ] Windows 系统重启。
- [ ] Windows 关机。
- [ ] 操作前显示未完成任务警告。
- [ ] 与 ComfyUI start / stop / restart 清晰区分。

## Deferred — 远程唤醒、开机与机外能力

当前 Remote Panel 运行在目标工作站上，机器关机后 Panel 自身无法完成开机。暂缓：

- Wake-on-LAN；
- 路由器 / NAS / 树莓派 / 其他常在线设备代发 WoL；
- 智能插座 + BIOS 来电自启；
- 机外 watchdog / agent。

## Deferred — 多主机

继续保留现有架构解耦成果，但暂不开发实际多主机 UX：

- AuthProvider 保留；
- Workflow Registry / revision / artifact 保留；
- 不新增 Host Registry、Machine Selector、per-job host routing。

多主机留给后续版本再评估。
