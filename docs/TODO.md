# Comfy Remote Roadmap / TODO

当前稳定开发基线：**v0.4.7 FL2VA Workflow Family & Inference Profile（In progress）**。

`v0.3 Public Readiness + Configurator 2.0` 已结束功能开发并完成合并；`v0.4 Creation Experience`、`v0.4 Recovery Lite`、`v0.4.1 Media Continuity`、`v0.4.2 H3 FL2VA Unified Modes`、`v0.4.3 Task Reconciliation Hardening`、`v0.4.4 Windows Environment Self-Healing`、`v0.4.5 Artifact History Sync & Ollama Model Setting` 与 `v0.4.6 FL2VA Multi-Backend Prompt Standardization` 均已完成当前范围收尾。

## v0.4.7 FL2VA Workflow Family & Inference Profile — In progress

- [x] 建立 9 个 canonical FL2VA asset 及中英文 Workflow Asset Inventory。
- [x] 用 manifest-backed resolver 解析 `3 generation modes × 3 prompt backends`，保留旧 ID 作为兼容资产。
- [x] 将 raw / Ollama / Qwen3.5 的输入、输出和 Prompt 捕获契约写入 manifest。
- [x] Qwen3.5 完成任务后延迟补抓标准化 Prompt，并支持历史成功任务扫描。
- [x] 推理配置保存到既有 `input_values_json`；当前 `auto` 解析到真实 INT8 资产，未声明的 FP16/BF16 变体拒绝执行。
- [ ] 完成全量 pytest、构建、仓库检查和 Windows + ComfyUI 真机 3 × 3 验收。
- [ ] 完成 v0.4.7 分支提交、CI 和 PR 合并收尾。

---

## v0.3 Public Readiness — Completed

### 完成范围

- [x] H3 与核心架构解耦；H3 作为 Bundled / Verified examples，不再是安装前提。
- [x] 普通 ComfyUI API Workflow 作为一等能力。
- [x] Public CLI：`setup`、`start / stop / restart / status`、`doctor`、`autostart`。
- [x] Windows Setup Wizard：自动/手动发现 ComfyUI、配置生成、旧配置备份与更新。
- [x] Windows Portable 启动脚本发现，保留真实启动参数，包括 `--enable-manager` 和可选 `--use-sage-attention`。
- [x] Panel 后台进程控制、health/status、未知端口占用保护。
- [x] Windows 登录自启动；Task Scheduler 权限不足时提供用户级 fallback。
- [x] Tailscale 检测、身份授权、Serve 配置与 Doctor 检查。
- [x] Doctor `PASS / WARN / FAIL` 与 `doctor --report` 隐私脱敏。
- [x] Configurator 2.0：统一 Workflow 分析模型、`/object_info` schema、图连接分析、heuristic fallback、置信度与 Preflight。
- [x] 不要求工作流固定包含 `width / height / batch_size`。
- [x] required media、通用 image/video/audio/file artifact、Runtime Test 与 revision 绑定。
- [x] WAI txt2img / img2img 与 H3 回归覆盖。
- [x] Windows 首次安装路径、Panel 黑窗、ComfyUI 可见控制台、Doctor H3 optional severity、Autostart 启动语义等真机问题完成修复。
- [x] README / Windows Getting Started / Troubleshooting / Workflow / Security / Contributing 公共文档体系。

### 真机验收记录

v0.3 在独立 Windows 环境完成了以下真实链路验证：

```text
干净安装
→ setup
→ Panel start / stop / status
→ ComfyUI lifecycle start / stop / restart
→ 普通 API Workflow 导入 / Preflight / 真实生成
→ 任务结果查看
→ Tailscale 配置路径
→ Windows autostart 注册
```

还使用了“存在 H3 nodes/workflows、但没有复制 H3 models”的环境验证：H3 缺可选模型应只影响对应内置工作流，不再把通用 Comfy Remote 安装错误判定为 `NOT READY`。

v0.3 最终发布定位为 **Public Beta**：核心路径可用，但不把高级恢复、多主机、WoL 等后续能力包装成已完成能力。

---

## v0.4 Creation Experience — Completed

本阶段目标是把创作页从 H3 优先的历史结构收敛成明确的 Specialized / Generic 双路径，并完成手机端真实工作流体验验收。

### 完成范围

- [x] Specialized 与 Generic 在数据源和 renderer 层明确分离；Generic 不再继承 H3 的 `beta / euler / 8` 等默认控件。
- [x] Generic 高级参数只来自 Configurator 保存的真实 Workflow binding；没有真实 `node / input` binding 的控件不得出现在创作页。
- [x] Generic 生成设置仅在真实绑定 `width / height / batch_size` 时显示；WAI img2img 跟随源图时不再出现空的“生成设置”。
- [x] Seed Policy：`randomize / fixed / increment`；随机策略隐藏数值 Seed，固定/递增策略显示数值输入。
- [x] 参考图分辨率预处理：保持原图 / 0.5 / 1.0 / 1.5 / 2.0 MP；保持比例、不放大小图，并覆盖 JPG/PNG/WebP 与 EXIF orientation。
- [x] Prompt 移动端输入改为稳定的原生 focus/blur 行为；移除会引起整页重排的 `prompt-focused` 模式，不增加自定义“收起键盘”按钮。
- [x] 工作流切换时 H3 / Generic 控件可正确恢复且不互相污染。
- [x] WAI Generic 高级参数、参考素材、Prompt、Seed、生成设置边界与真实生成链路通过移动端实机验收。
- [x] Windows/Linux、Python 3.11/3.13、minimum-dependencies、repository-safety、pytest、JS syntax check 与 build 全部通过。

### 真机验收记录

2026-08-29 完成 Creation Experience 收尾验收：

```text
H3 Specialized ↔ WAI Generic 多次切换
→ Generic 仅显示真实绑定参数
→ Seed 策略显示/隐藏符合预期
→ Prompt 键盘进入/退出稳定，无明显布局抖动
→ WAI img2img 上传参考图后不出现空“生成设置”
→ 用户确认验收通过
```

---

## v0.4 Recovery Lite — Completed

本阶段只解决一个现实问题：**人在外面时，如果 ComfyUI 崩溃、卡死或失联，手机端能够判断问题，并安全地手动恢复 ComfyUI。**

### 完成范围

- [x] 设备状态收敛为用户可理解的 `在线 / 离线 / 无响应`；Panel 与 ComfyUI 状态明确分开。
- [x] `无响应` 由“ComfyUI API 不可用 + 已记录且重新核验通过的 ComfyUI 主进程仍存活”判断，不依赖模糊的最近成功窗口。
- [x] 新增人工 `force_restart`：只允许对 Remote Panel 已记录并重新核验 PID / create time / executable / command line 的 ComfyUI 主进程执行。
- [x] 强制关闭仅处理从已验证 ComfyUI 主进程实时枚举出的进程树；每个目标在终止前再次核验进程实例，禁止按 `python.exe`、端口或模糊进程名批量杀进程。
- [x] ComfyUI 正常在线时拒绝 `force_restart`，要求使用普通重启；只有离线但已验证进程仍存活等恢复场景才开放强制重启。
- [x] 设备页显示 Remote Panel / ComfyUI 两个独立状态；ComfyUI 无响应时出现“强制重启”并进行二次确认，存在未完成任务时明确提示会中断。
- [x] 任务卡对已有 `cuda_oom / missing_model / missing_node / output_missing / comfyui_disconnected` 分类显示更清楚的用户提示，不增加任务自动续跑。
- [x] 回归测试覆盖：offline / unresponsive 判定、PID 实例变化保护、进程树限制、在线状态拒绝强制重启、前端脚本注入与 JS syntax check。
- [x] Windows 真机验收：ComfyUI 正常在线、普通 restart、关闭后重新 start 均通过。
- [x] Windows 可见控制台恢复正常日志输出；Panel 启动后不再只出现纯黑 ComfyUI 控制台。
- [x] 设置 → 关于可查看版本、分支、提交与工作区状态，用于确认真机验收版本对齐。
- [x] 当前范围真机验收通过，CI 在 Windows/Linux、Python 3.11/3.13、minimum-dependencies、repository-safety、pytest、JS syntax 与 build 全部通过。

### 延后真实事故验证

以下能力已实现并由自动化测试覆盖，但**不为了验收主动制造真实 CUDA OOM / 卡死事故**：

- 真实爆显存后 ComfyUI 进程仍在但 API 无响应时，设备页能否稳定进入“无响应”；
- 真实卡死后的“强制重启”能否完成现场恢复；
- 极端情况下失效 process record 的拒绝强杀保护。

这些场景在后续真实遇到时再做补充真机验收，不阻塞 Recovery Lite 当前阶段收尾。

### 明确不做

Recovery Lite 不加入以下复杂能力：

- watchdog / 后台自动拉起；
- 自动重试、指数退避、crash-loop 管理；
- 任务自动恢复、自动续跑或重新提交；
- 更复杂的 queue/history reconciliation；
- Panel 重启后的生成现场恢复；
- GPU / driver 级自动诊断；
- Windows 睡眠 / 休眠 / 系统重启恢复；
- Wake-on-LAN；
- 多主机。

完成标准：**正常时不添麻烦；需要人工恢复时提供受控能力；任何无法确认进程身份的情况都宁可拒绝恢复，也不能误杀其他进程。**

---

## v0.4.1 Media Continuity — Completed

本阶段不引入新的 Asset 架构，只补齐创作历史与实际产物信息的连续性和可靠性。

### 完成范围

- [x] Retry API 返回 retained media 的 artifact identity，不暴露本机路径。
- [x] 历史参考图通过受认证的 Job input endpoint 恢复真实预览；不伪造浏览器 `File` / `Blob`。
- [x] Retry 只改 Prompt 时可直接沿用历史素材，不要求手机重新选择或上传同一文件。
- [x] retained 素材支持替换 / 删除；每个 Job 继续持有独立私有文件副本，历史 Job 不被新任务修改。
- [x] 图片分辨率策略与 target MP 未变化时复用保存的处理元数据并跳过重复预处理；策略变化时只处理新 Job 的私有副本。
- [x] 图片任务展示真实产物的宽×高、格式和文件大小；旧任务在访问历史时按需 lazy backfill。
- [x] `job_artifacts.metadata_json` 采用 additive schema 扩展，不改变既有 SQLite rollback compatibility marker。
- [x] 历史图片使用原生 `loading="lazy"` / `decoding="async"`，不增加新的 Observer 体系。
- [x] Recovery Lite `无响应` 增加连续失败 3 次防抖：前两次不判无响应、不提供强制重启；第 3 次且已核验受管进程仍存活时才进入无响应；任意一次健康检查成功即清零失败计数。
- [x] H3 / Generic、Seed Policy、Prompt 手机键盘、Settings、Recovery Lite 等 v0.4 基线未发现回归。

### 验收记录

2026-08-29 完成手机端真实验收，覆盖：

```text
H3 ↔ Generic
→ Retry 后历史参考图真实预览
→ 只改 Prompt 再生成
→ A → B → C 连续 Retry
→ retained 图片 Replace / Delete
→ 1.0 MP → 1.0 MP
→ 1.0 MP → 0.5 MP
→ Never Upscale
→ WAI txt2img / img2img 实际文件尺寸与 UI 对照
→ Settings / Recovery Lite 回归
→ 用户确认未发现问题
```

卡死场景不主动制造；连续 3 次失败防抖由自动化测试验证，包括“前两次不进入无响应”“第 3 次进入无响应”“成功一次后计数归零”。

---

## v0.4.2 H3 FL2VA Unified Modes — Completed

本阶段把三个 H3 FL2VA 物理工作流收敛成一个用户侧能力入口，同时保留物理工作流本身与各自启用状态。

### 完成范围

- [x] 新增虚拟入口 `h3-fl2va-group`，映射 `original / lightx2v / v4_600step` 三种生成模式。
- [x] 首次默认 `v4_600step`；浏览器只记忆 FL2VA 的模式偏好，Retry 恢复被重试任务实际使用的模式。
- [x] 创作页只显示一个 `MiniMax H3 FL2VA` 产品入口；Workflow Manager 继续保留三个物理工作流。
- [x] 高级设置暴露 H3 提示词标准化开关，默认开启；标准化器使用独立随机隐藏 seed。
- [x] 标准化提示词从 ComfyUI `PreviewAny` 实际 history 输出捕获并持久化，不由 Panel 二次重算。
- [x] 任务详情中原始提示词与标准化提示词相邻展示；外层任务卡只保留原始提示词。
- [x] H3 reference aspect 改由工作流自身 `H3AspectRouter` 决策；参考图预处理继续 downscale-only、保持比例且不放大小图。
- [x] 修复 generation mode 切换、Retry aspect 摘要、重复 `values_json`、标准化开关样式等回归。
- [x] CI 与回归测试通过后合并到 main。

---

## v0.4.3 Task Reconciliation Hardening — Completed

本阶段只处理一次真实暴露出的任务最终状态竞态：ComfyUI 实际执行成功，但 Panel 可能在重启或 history 落盘时序窗口中误判为失败。

### 完成范围

- [x] 不完整 / 暂态 history 不再因为“尚未明确 success”而直接进入 `failed`。
- [x] WebSocket `execution_success` 本身作为明确成功证据，即使 `/history/<prompt_id>` 仍暂时为空也不会写入 generic failure。
- [x] history 只有 `execution_success` message、但 `completed/status_str` 尚未同步时，先规范化为成功再进入旧 reconciliation 层。
- [x] `execution_error` / `execution_interrupted` 继续保持明确终态优先级；延迟 success 不得覆盖具体失败。
- [x] 对 v0.4.2 已落库的 exact generic false-failure，只在 ComfyUI history 仍有明确 success 时允许修正并重新捕获输出。
- [x] 不通过残留 MP4 文件名反推成功；ComfyUI history 已清除的旧误判任务保持原状态，避免文件系统反向定义任务状态。
- [x] 中英文 Troubleshooting、Changelog、版本号与路线图同步到 v0.4.3。

### 验证边界

- 自动化覆盖 empty/not-ready history、ambiguous history、message-only success、explicit error、旧 generic false-failure 的 history-backed repair，以及已有并发终态优先级回归。
- 该竞态难以稳定在真实设备上人工复现；本次不要求为了验收主动制造概率性故障，自动化与 CI 作为主要收尾依据。

---

## v0.4.4 Windows Environment Self-Healing — Completed

本阶段针对 Windows 项目环境损坏后的安装/修复路径做加固，目标是让已有 `.venv` 不能因为“文件还在”就被误认为可用。

### 完成范围

- [x] `Install-ComfyRemote.ps1` 会真正启动已有 `.venv`，检查核心标准库与 `pip`，而不是只判断 `python.exe` 是否存在。
- [x] `.venv` 健康时继续复用；损坏时先保留为 `.venv.broken-YYYYMMDD-HHMMSS`，再用健康的稳定版基础 Python 重建。
- [x] 新创建的 `.venv` 在继续安装前再次做健康检查；`pip install -e .` 完成后再验证 `comfyui_remote_panel` 可以正常 import。
- [x] `.venv` 继续作为 Panel 的标准运行环境；全局/基础 Python 只承担前置检查和创建项目环境，不作为静默长期 fallback。
- [x] Windows 启动脚本与 Task Scheduler 注册路径都支持绝对 `PythonPath`；安装器同时支持绝对 `ConfigPath`。
- [x] 文档明确区分日常更新与完整安装/修复：正常更新为 `git pull` + Panel `restart`；只有依赖/安装元数据、Setup/配置或环境修复场景才重新运行安装器。
- [x] 回归测试覆盖健康检查、坏环境备份重建、新环境验证、包 import 验证、绝对路径处理与 PowerShell 语法检查。
- [x] Windows/Linux、Python 3.11/3.13、minimum-dependencies、repository-safety、pytest 与 build CI 通过。

---

## v0.4.5 Artifact History Sync & Ollama Model Setting — Completed

### 完成范围

- [x] 已登记 output artifact 与本地受管文件同步；本地生成产物被删除/移走后，对应失效 artifact 自动移除，全部产物消失后 Job 从历史移除。
- [x] 多输出 Job 保留仍存在的输出；从未登记输出的失败/中断 Job 不因本地无文件而被误删。
- [x] Purge 同步清理已登记 artifact 与历史输入，不依赖单一 legacy output 记录。
- [x] H3 FL2VA 的 Ollama 标准化模型可在高级设置中配置，默认 `gemma4:e4b`；选择写入 Job 并由 Retry 恢复。
- [x] 不引入 Ollama 启停、模型下载/删除或模型列表管理层。

---

## v0.4.6 FL2VA Multi-Backend Prompt Standardization — Completed

### 完成范围

- [x] 用户侧继续只有一个 `MiniMax H3 FL2VA` 入口，生成模式保持 `original / LightX2V / v4_600step`。
- [x] “标准化提示词”改为 `关闭 / Ollama / ComfyUI` 三态；Ollama 复用现有链路，ComfyUI 路由到三套 Qwen3.5 4B 物理工作流。
- [x] 三套 Qwen 工作流对齐 v4.4 API graph，保留对应生成模式的模型、LoRA、scheduler、sampler、steps 和参考帧路由。
- [x] Retry 恢复实际生成模式与标准化后端；修复前端 observer 覆盖 Retry 恢复值的问题。
- [x] 修复 FL2VA 隐藏 preset 漂移到 Ref2VA、reference aspect 丢失和默认画幅漂移问题。
- [x] 任务进度按 `prepare / standardize / sampling / decode / compose / save` 语义展示；排队、标准化、采样、总执行耗时分开记录和展示。
- [x] 任务卡按实际组合显示 `LightX2V / v4_600step / Ollama / Qwen3.5 4B` 标签，不给 original/关闭增加额外标签。
- [x] Qwen 标准化 Prompt 优先从保存节点 metadata 捕获，history 未暴露 metadata 时回退到连接 Qwen writer 的 `PreviewAny(177)`，继续写入统一的 `standardized_prompt` 字段。
- [x] 设备页增加受控“强制关闭”：当 Panel 缺失进程记录、但能唯一安全识别当前 ComfyUI 监听进程时允许关闭，不按模糊 `python.exe` 批量杀进程。
- [x] 设备概览仅在当前实际 ComfyUI 监听进程命令行包含 `--use-sage-attention` 时显示 `SageAttention` 状态框；不读取配置文件猜测运行态。
- [x] 版本号、CHANGELOG、README、v0.4.6 专项中英文文档和回归测试同步。

### 真机验收记录

2026-08-31 至 2026-09-01 在目标 Windows / RTX 4080 SUPER / 手机远程环境持续实测：

```text
FL2VA 单入口与高级设置三态
→ v4_600step + ComfyUI Qwen3.5 4B 多次真实生成
→ 任务卡/详情耗时与运行标签
→ Retry 恢复标准化后端
→ 设备页安全识别非 Panel 托管 ComfyUI 并显示“强制关闭”
→ 现场确认 Codex 手动重启 ComfyUI 导致 PID/启动参数变化，Panel 未误认成受管进程
```

Qwen 标准化 Prompt 的 history fallback 与 SageAttention 状态探测由自动化回归覆盖；真实 GPU / Custom Node 的极端显存和硬卡死行为仍属于现场继续观察项，不阻塞 v0.4.6 收尾。

---

## Later / separate design tracks

这些方向可以继续研究，但不自动并入 Recovery Lite / v0.4.6：

- Ref2VA grouped workflow：沿用 v0.4.2 的产品级模式路由，把三个 H3 Ref2VA 物理工作流收敛成一个用户入口；建议作为后续独立 feature branch。
- Full Reliability / Watchdog：自动拉起、重试退避、crash-loop、防断线误判、任务最终状态 reconciliation 等完整无人值守恢复能力。
- Multi-host：家里 / 公司 / 其他主机的 Host Registry、selector、routing。
- Wake-on-LAN / external watchdog：依赖局域网或机外常驻设备的电源恢复。
- Web i18n / Language switch：重构为 key-based `t()` + 中英文语言包 + 显式 rerender；不再使用全局 DOM 扫描或 `MutationObserver` 追踪翻译。当前网页端继续保持中文稳定版，CLI / 文档双语不受影响。
- Media optimization：视频缩略图、远程预览带宽优化，以及参考图预处理策略的后续增强。
- Additional transports：在不降低安全边界的前提下补充 Tailscale 之外的连接方式。

路线图原则：**先解决真实远程使用痛点，再决定是否值得引入更复杂的无人值守恢复、多主机或媒体资产系统。**
