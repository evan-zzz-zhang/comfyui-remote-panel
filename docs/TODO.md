# Comfy Remote Roadmap / TODO

当前开发基线：**v0.4 Recovery Lite**。

`v0.3 Public Readiness + Configurator 2.0` 已结束功能开发并完成合并；`v0.4 Creation Experience` 已完成开发、CI 与移动端真机验收。当前只做一层轻量人工恢复能力，不把完整 watchdog / 自动恢复系统一次性塞进 v0.4。

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

## v0.4 Recovery Lite — Current baseline

本阶段只解决一个现实问题：**人在外面时，如果 ComfyUI 崩溃、卡死或失联，手机端能够判断问题，并安全地手动恢复 ComfyUI。**

### 当前范围

- [x] 设备状态收敛为用户可理解的 `在线 / 离线 / 无响应`；Panel 与 ComfyUI 状态明确分开。
- [x] `无响应` 由“ComfyUI API 不可用 + 已记录且重新核验通过的 ComfyUI 主进程仍存活”判断，不依赖模糊的最近成功窗口。
- [x] 新增人工 `force_restart`：只允许对 Remote Panel 已记录并重新核验 PID / create time / executable / command line 的 ComfyUI 主进程执行。
- [x] 强制关闭仅处理从已验证 ComfyUI 主进程实时枚举出的进程树；每个目标在终止前再次核验进程实例，禁止按 `python.exe`、端口或模糊进程名批量杀进程。
- [x] ComfyUI 正常在线时拒绝 `force_restart`，要求使用普通重启；只有离线但已验证进程仍存活等恢复场景才开放强制重启。
- [x] 设备页显示 Remote Panel / ComfyUI 两个独立状态；ComfyUI 无响应时出现“强制重启”并进行二次确认，存在未完成任务时明确提示会中断。
- [x] 任务卡对已有 `cuda_oom / missing_model / missing_node / output_missing / comfyui_disconnected` 分类显示更清楚的用户提示，不增加任务自动续跑。
- [x] 回归测试覆盖：offline / unresponsive 判定、PID 实例变化保护、进程树限制、在线状态拒绝强制重启、前端脚本注入与 JS syntax check。
- [ ] Windows 真机验收：正常在线、正常 restart、手动关闭后重新 start。
- [ ] Windows 真机验收：安全模拟“进程仍在但 API 无响应”，手机显示“无响应”并完成强制重启。
- [ ] Windows 真机验收：伪造/失效 process record 时必须拒绝强杀，不能影响其他 Python 进程。
- [ ] 真机验收通过后同步用户文档 / ACCEPTANCE，创建 PR 并合并 `main`。

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

完成标准：**正常时不添麻烦；ComfyUI 卡死时能从手机安全恢复；任何无法确认进程身份的情况都宁可拒绝恢复，也不能误杀其他进程。**

---

## Later / separate design tracks

这些方向可以继续研究，但不自动并入 Recovery Lite：

- Full Reliability / Watchdog：自动拉起、重试退避、crash-loop、防断线误判、任务最终状态 reconciliation 等完整无人值守恢复能力。
- Multi-host：家里 / 公司 / 其他主机的 Host Registry、selector、routing。
- Wake-on-LAN / external watchdog：依赖局域网或机外常驻设备的电源恢复。
- Web i18n / Language switch：重构为 key-based `t()` + 中英文语言包 + 显式 rerender；不再使用全局 DOM 扫描或 `MutationObserver` 追踪翻译。当前网页端继续保持中文稳定版，CLI / 文档双语不受影响。
- Media optimization：视频缩略图、远程预览带宽优化，以及参考图预处理策略的后续增强。
- Additional transports：在不降低安全边界的前提下补充 Tailscale 之外的连接方式。

路线图原则：**先解决真实远程恢复痛点，再决定是否值得引入完整无人值守恢复系统。**
