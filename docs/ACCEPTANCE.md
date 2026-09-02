# Comfy Remote 实机验收 / Release Acceptance

自动化测试不替代真实模型、真实工作流和手机网络验收。本文件持续记录已完成阶段的真机验收结果。

## v0.2 Comfy Remote 移动端 UX

- 首页品牌显示 **Comfy Remote**，不再显示“H3 生成台”。
- 主导航仅为 **创作 / 任务 / 设备**；工作流管理从右上角设置进入。
- 创作、任务、设备页正文不再重复显示同名大标题；设置和工作流等子页面仍保留页面标题。
- 任务页不显示独立刷新按钮；点击“任务”标签会加载 / 刷新任务，在任务页再次点击也会刷新。
- 在 360、390、430 px 宽度检查无关键横向溢出、文字遮挡或不可点击控件。
- 工作流选择使用移动端选择面板；切换工作流后参考素材、提示词和基础设置同步重绘。
- 点击 Prompt 后键盘状态下输入框仍可编辑、生成按钮可触达，关闭键盘后页面恢复。
- 生成设置面板只展示当前工作流支持的基础参数。
- 图片与视频工作流均遵循：**工作流 → 参考素材 → Prompt / 负面 Prompt → 生成设置 → 高级设置 → 生成**。
- 任务卡不常驻显示 Prompt 正文；任务详情显示唯一一份完整 Prompt，并提供轻量一键复制。
- 图片任务显示图片结果；视频任务可直接播放。
- `Sampler / Scheduler / Steps / Seed / Workflow Revision` 等技术信息默认不占任务卡主视觉。

## v0.2 三类基准工作流

### FL2VA

- 纯文字、仅首帧、仅尾帧、首尾帧链路通过实机验证。
- 首帧/尾帧、替换、画幅、5–15 秒时长和 0.2–1.0 MP 设置通过验证。
- 固定画幅 UI 顺序为：`9:16 / 16:9 / 1:1 / 3:4 / 4:3 / 21:9`；不显示 `2:3 / 3:2`。
- “参考图”位于固定画幅之后：首帧优先、尾帧回退，无图片时不可选。
- UI 重构未改变工作流 graph 的 sampler、scheduler、steps、denoise、LoRA/Sigma Shift 和 24 fps 等执行定义。
- 视频预览、拖动、下载和基础“再次生成”通过验证。

### Ref2VA

- 多参考图、参考视频和参考音频链路通过验证。
- 参考素材可统一管理，添加、替换、删除和数量限制正常。
- `<Picture 1>`、`<Video 1>`、`<Audio 1>` 指代顺序与素材顺序一致。
- 固定画幅之后依次显示“参考图”“参考视频”；无对应素材时不可选择。
- 参考画幅、时长、分辨率通过验证。
- 基础“再次生成”可继续沿用 retained 素材；完整可视化生成现场恢复留到后续版本。

### 普通生图 / WAI API Workflow

已使用真实、非内置 H3 的 ComfyUI API Workflow 完成验收：

- 设置 → 工作流 → 导入 API Workflow。
- 自动识别正面提示词、负面提示词、参考图、width、height、batch_size 和主要图片输出。
- 保存后可从创作页选择并真实生成。
- 正负 Prompt、参考图、宽高和生成数量可按工作流声明修改。
- “生成设置”位于“高级设置”之前。
- 图片结果、多图展示、结果查看、下载和基础“再次生成”通过验证。

## v0.2 工作流管理

- 六个内置 H3 工作流可修改前端显示名称；内部 workflow ID 不改变。
- 工作流列表开关的日常语义是 **显示在创作页 / 隐藏**，点击即时反馈并后台持久化。
- 隐藏的工作流不出现在普通创作页选择器，但历史任务和再次生成能力不丢失。
- 工作流“全部 / 视频 / 图片”筛选真实生效。
- 自定义工作流导入、编辑高级映射、测试、复制、导出和删除均通过验收。
- 自定义工作流删除为真实删除，操作后管理列表和创作 preset 立即同步，无需重启 Remote Panel；历史任务快照不受影响。
- 同 ID 新 revision 不影响旧任务保存的 workflow snapshot 和 input values。

## v0.2 任务与队列

- 排队、提交、运行、完成、取消和失败场景通过验收。
- 任务卡保持作品优先，不常驻显示 Prompt。
- 任务详情完整 Prompt 可阅读并可一键复制。
- 失败摘要不会泄露本机绝对路径或地址。
- 图片与视频结果均可正确读取，不在任务列表初始化时批量预加载大文件。

## v0.2 恢复与文件

- Panel 任务恢复、SSE 快照、MP4 Range 播放和下载链路已经过阶段性验证。
- 视频缩略图偶发不稳定作为独立后续专项，不用 UI 无限 reload 视为解决。
- “移出历史”只隐藏任务并保留本地输入/输出；显式 purge 才物理清理登记文件。
- 输出缺失恢复机制与 `output_missing` 终态由自动化测试覆盖。

## v0.2 设备与网络

- 面板继续只监听 `127.0.0.1:8190`，ComfyUI 为本机 `8188`。
- 缺失或错误身份信息访问受保护接口返回 403。
- 手机经 Tailscale HTTPS 完成远程访问、生成、播放/查看结果和下载。
- ComfyUI start / stop / restart 与 GPU、显存、温度、功耗、RAM 状态已完成阶段性实机验证。

CI release gates：minimum-dependencies、Windows/Linux、Python 3.11/3.13、tests、repository scan、wheel/source build。

---

## 2026-08-25 阶段验收记录

- Remote Panel 已重新启动并加载本轮修复，继续只监听 `127.0.0.1:8190`；`/healthz` 返回 200。
- 匿名 jobs API 返回 403，授权首页返回 200，跨来源设备控制写请求返回 403。
- 六套预设均可加载；现有任务通过 jobs API 返回，seed 为十进制字符串。
- 真实 ComfyUI 启动成功；进程记录包含 PID、create time、executable、command line并与运行中主进程一致。
- Remote Panel 远程关闭 ComfyUI 成功：只关闭记录的主 PID，8188 停止监听，8190 保持健康。
- IPv6 开启后，移动 5G 已恢复 Tailscale Direct，并可查看已生成视频。
- Tailscale HTTPS 手机端实测通过。

## 2026-08-25 资源边界与前端验收记录

- Python 自动化测试、仓库安全扫描、JavaScript 语法检查、sdist 与 wheel 构建通过。
- SQLite 本机基准、延迟上传双击防重、历史分页、SSE、移动视口等阶段性验证通过。

## 2026-08-25 vivo X300 移动实机反馈

- 环境：vivo X300、Microsoft Edge、中国广电 5G、Tailscale 已连接。
- 纯文字、仅首帧、仅尾帧四种 FL2VA 均成功；Ref2VA 真实任务成功。
- 生成、播放、拖动和下载整体通过。

## 2026-08-26 Mobile UX Rebuild 最终验收

- `docs/UI_VISUAL_SPEC.md` 已确立为当前移动端视觉基线。
- 用户确认 **UI 部分验收通过**。
- 用户确认 **自定义工作流导入与管理验收通过**。
- 用户确认 **FL2VA / Ref2VA / 自定义图片工作流真实生成及最终功能验收通过**。
- 自定义工作流删除已修正为真实、即时删除；导出按钮换行问题已修复并通过回归。
- 最新功能提交后的 CI 在 minimum-dependencies、Ubuntu/Windows、Python 3.11/3.13 上全部通过。
- “生成现场恢复”、视频缩略图稳定性、高清参考图自动压缩、Windows 工作站生命周期均明确转入 `docs/TODO.md` 后续阶段，不阻塞 v0.2 发布。

**结论：Comfy Remote v0.2 满足发布条件。**

---

## 2026-08-29 v0.4 Creation Experience 最终验收

本轮在 `feat/v0.4-creation-experience` 完成 Specialized / Generic 创作体验收敛，并经过真实手机操作确认。

### Renderer 与参数边界

- H3 Specialized 与 Generic imported workflow 分离；WAI 页面不再泄漏 H3 `Scheduler beta / Sampler euler / Steps 8`。
- WAI Generic 高级设置只显示 Configurator 保存的真实 Workflow binding，包括 Steps、CFG、Sampler、Scheduler、Denoise、Checkpoint、Seed 等实际已绑定参数。
- Generic 没有真实 `width / height / batch_size` binding 时不显示“生成设置”。
- WAI img2img 上传参考图后不再因为“跟随源图 / 数量由工作流决定”等只读 capability summary 重新打开空“生成设置”。
- H3 → WAI → H3 → WAI 切换后 Specialized / Generic 控件可正确恢复，不互相污染。

### Seed 与参考图

- Seed 策略 UI 验收通过：Random 只显示 Seed 策略；Fixed / Increment 显示数值 Seed 输入。
- 参考图分辨率控制保持在高级设置中；支持保持原图 / 0.5 / 1.0 / 1.5 / 2.0 MP。
- 图像预处理保持宽高比，不放大小图；自动化覆盖 JPG / PNG / WebP、EXIF orientation 与目标 MP 计算。
- Ref2VA 参考视频不受参考图 MP 预处理影响，保持当前行为。

### Prompt 移动体验

- 移除旧 `prompt-focused` 模式；进入/退出输入时不再隐藏整页、改变生成按钮布局或把 textarea 扩展为 `40dvh`。
- Prompt 输入框聚焦前后保持稳定尺寸，手机端不允许手动 resize。
- Prompt 外层不再依赖巨大 `<label>` 导致 blur 后重新 focus；点击 textarea 外可自然收起键盘。
- 不增加“收起键盘”按钮，不重新启用全局 MutationObserver。
- 用户确认 Prompt 输入框退出问题及明显布局抖动已解决。

### CI 与结论

- minimum-dependencies：通过。
- repository-safety：通过。
- Windows Python 3.11 / 3.13：通过。
- Ubuntu Python 3.11 / 3.13：通过。
- pytest、JavaScript syntax check、repository scan、wheel/source build：通过。
- 用户最终确认 WAI img2img 空“生成设置”修复通过。

**结论：v0.4 Creation Experience 真机验收通过，可以合并到 `main` 作为下一阶段 Reliability / Recovery 的稳定基线。**

---

## 2026-08-29 v0.4 Recovery Lite 最终验收

本轮在 `feat/v0.4-recovery-lite` 完成轻量人工恢复能力，并按当前范围完成 Windows 真机验收。

### 当前范围已通过

- 设备页将 Remote Panel 与 ComfyUI 状态分开显示，用户可区分 Panel 在线与 ComfyUI 在线状态。
- ComfyUI 正常在线时，启动 / 关闭 / 普通重启均可从移动端稳定控制。
- Panel 启动后由其拉起的 ComfyUI 可见控制台恢复正常日志输出，不再只出现纯黑窗口。
- 设置 → 关于可正常打开和返回，并显示当前版本、分支、提交与工作区状态，用于确认真机验收版本对齐。
- Recovery Lite 的强制重启后端仅允许操作经过 PID / create time / executable / command line 核验的 ComfyUI 进程实例；进程树限制与拒绝误杀由自动化测试覆盖。
- ComfyUI 正常在线时不开放强制重启，避免把危险恢复动作当作普通控制使用。
- 任务错误提示已覆盖 `cuda_oom / missing_model / missing_node / output_missing / comfyui_disconnected` 等已存在分类。

### 延后真实事故验证

本轮**不主动制造真实 CUDA OOM、GPU 卡死或 ComfyUI 假死事故**。因此以下能力暂记为“实现并有自动化保护，但等待真实现场补充验收”：

- 真实爆显存后“进程仍在、API 无响应”的状态识别；
- 真正卡死后的“无响应 → 强制重启”现场恢复；
- 极端情况下失效 process record 的真机拒绝强杀验证。

用户确认：这些场景以后真实遇到时再验，不作为当前 Recovery Lite 合并 `main` 的阻塞项。

### CI 与结论

- minimum-dependencies：通过。
- repository-safety：通过。
- Windows Python 3.11 / 3.13：通过。
- Ubuntu Python 3.11 / 3.13：通过。
- pytest、JavaScript syntax check、repository scan、wheel/source build：通过。

**结论：v0.4 Recovery Lite 当前范围真机验收通过。真实 OOM / 卡死恢复保留为后续现场验证项，不阻塞本阶段合并与收尾。**

---

## 2026-08-29 v0.4.1 Media Continuity 最终验收

本轮在 `feat/v0.4.1-media-continuity` 完成 Retry 历史素材连续性与实际图片产物元数据，并在发布收尾时加入 Recovery Lite 无响应三次连续失败防抖。

### 手机真机验收通过

- H3 ↔ Generic 工作流切换未发现回归。
- 手机 Prompt 键盘进入、编辑、退出未发现回归。
- Retry 后历史参考图恢复真实预览，不再只有“已保留素材”占位。
- 仅修改 Prompt 可直接再次生成，不要求重新选择参考图。
- A → B → C 连续 Retry 可持续沿用参考素材。
- retained 图片 Replace / Delete 行为符合预期，历史 Job 不被后续任务修改。
- 1.0 MP → 1.0 MP、1.0 MP → 0.5 MP 与 Never Upscale 路径未发现异常。
- WAI txt2img / img2img 任务卡显示的实际输出尺寸与产物文件对照通过。
- Settings 与 Recovery Lite 回归未发现问题。
- 用户完成整轮验收后确认：**未发现问题**。

### 无响应防抖自动化验收

由于不主动制造真实 GPU / ComfyUI 卡死事故，本项按用户授权由自动化验证完成：

- 已核验受管 ComfyUI 进程仍存活时，第 1 次健康检查失败不判 `unresponsive`，且不开放强制重启。
- 第 2 次连续失败仍不判 `unresponsive`，且不开放强制重启。
- 第 3 次连续失败才判 `unresponsive` 并沿用 Recovery Lite 的受控强制重启能力。
- 任意一次健康检查成功都会把失败计数清零；之后再次失败从第 1 次重新累计。
- 未发现受管进程时仍直接按 `offline` 处理，不会因为失败次数误判为卡死。

### CI 与结论

- 防抖改动加入后，minimum-dependencies、repository/history safety、Ubuntu Python 3.11 / 3.13、Windows Python 3.11 / 3.13 的 pytest 与 build 全部通过。
- 最终发布 gate 要求版本、文档和代码位于同一提交链，并再次通过上述完整 CI 后合并；不以真实 GPU 卡死作为发布阻塞项。

**结论：v0.4.1 真机功能验收通过；卡死防抖由自动化覆盖并通过。满足最终发布 gate，合并仅在完整 CI 全绿后执行。**

---

## 2026-09-02 至 2026-09-03 v0.4.7 FL2VA Workflow Family 3 × 3 真机基线

本轮在目标 Windows / RTX 4080 SUPER / 手机远程环境，通过手机面板完成 9 个
canonical FL2VA 工作流的全量实测。最终一轮 9/9 任务均成功完成，并登记了
`video/mp4` 输出。本轮统一使用首帧输入、5 秒、0.4 MP、INT8 推理配置。

### 最终通过矩阵

| 生成模式 | Raw | Ollama | Qwen3.5 4B |
| --- | --- | --- | --- |
| `v4step600` | 通过（1:14） | 通过（2:04） | 通过（2:13） |
| `LightX2V` | 通过（1:08） | 通过（2:13） | 通过（1:59） |
| `original` | 通过（2:09） | 通过（3:24） | 通过（2:44） |

耗时为任务记录中的实际执行耗时，用于后续定位性能或阶段回归；不作为固定性能
承诺。最终 9 个 canonical preset 为：

```text
fl2va_v4step600_raw / fl2va_v4step600_ollama / fl2va_v4step600_qwen35
fl2va_lightx2v_raw / fl2va_lightx2v_ollama / fl2va_lightx2v_qwen35
fl2va_original_raw / fl2va_original_ollama / fl2va_original_qwen35
```

### 前置现场观察

在形成最终通过矩阵前，同一测试窗口曾出现三次前置异常：

- `v4step600 + Raw`：提交确认超时（`submission_unconfirmed`）；
- `v4step600 + Ollama`：任务结束后暂未找到输出（`output_missing`）；
- `v4step600 + Qwen3.5`：ComfyUI 执行期间离线，任务进入历史隐藏状态。

三项随后均重新提交并成功完成，因此不计入最终 3 × 3 失败项，但保留为真实现场
回归观察。后续代码、UI、任务状态、输出登记和 Retry 改动，都应以本节的 9/9
成功矩阵及上述异常恢复行为作为基线。

**结论：v0.4.7 FL2VA canonical 3 × 3 手机面板实机验收通过；全量自动化检查与
分支/CI 收尾仍未完成。**

## v0.4.8 Ref2VA Workflow Family — automated baseline

The v0.4.8 implementation adds nine Ref2VA canonical assets and keeps the three
legacy Ref2VA IDs available to the workflow manager and historical Retry path.
Automated/static checks cover the resolver, legacy mapping, one-time status
inheritance, sampling contracts, collection bindings, representative image and
video-first-frame selection, Qwen metadata wiring, inference-profile variants,
and the isolated browser `values_json` routing controls.

The target Windows / ComfyUI / RTX 4080 SUPER 9/9 INT8 matrix and the BF16
representative runs remain pending. No real-GPU success is claimed by this
baseline.
