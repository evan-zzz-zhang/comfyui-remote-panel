# Comfy Remote Roadmap / TODO

当前开发基线：**v0.4 Reliability / Recovery**。

`v0.3 Public Readiness + Configurator 2.0` 已结束功能开发并完成合并；v0.3.0 以 **Public Beta** 作为第一个面向公开用户的发布基线。

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

### v0.3 明确延后

以下内容没有为了 Public Readiness 临时塞入 v0.3：

- 高级生成现场恢复 / watchdog；
- Windows 睡眠、休眠、系统重启、关机；
- Wake-on-LAN；
- 多主机 Host Registry / routing / selector；
- 高清参考图自动压缩；
- 视频缩略图专项；
- 独立 Seed Policy（`randomize / fixed / increment`，可扩展 decrement）。

---

## v0.4 Reliability / Recovery — Current baseline

v0.4 的目标不是继续堆更多 Workflow 类型，而是让“已经能远程用”变成“长时间无人看守也更可靠”。

### 1. ComfyUI 故障恢复

- [ ] 明确定义 ComfyUI 状态：online / starting / stopping / crashed / unhealthy / unknown。
- [ ] 区分“API 暂时无响应”“ComfyUI 进程退出”“GPU/driver 级异常”。
- [ ] 任务执行期间 ComfyUI 异常时保留可解释的失败原因，而不是只显示连接断开。
- [ ] 增加受控的强制停止 / 进程树清理策略，避免误杀用户其他 Python 进程。
- [ ] 根据配置决定是否自动拉起 ComfyUI，并提供退避/最大重试，避免 crash loop。
- [ ] Panel 重启后恢复可恢复的 lifecycle / task 状态。

### 2. 任务可靠性

- [ ] 明确 submitted / queued / running / completed / failed / interrupted 的恢复语义。
- [ ] ComfyUI 断开后重新查询 history/queue，尽可能确认任务真实最终状态。
- [ ] 避免因 WebSocket/浏览器断线把仍在生成的任务误判失败。
- [ ] 提供更清楚的 OOM / missing model / custom node runtime / output missing 分类。
- [ ] 为恢复逻辑补充真实故障 fixture 与集成测试。

### 3. 设备页 Recovery UX

- [ ] 把“Panel 在线”和“ComfyUI 在线”明确分开。
- [ ] 显示最近一次 ComfyUI 崩溃/重启原因与时间。
- [ ] 对安全可恢复状态提供“重启 ComfyUI”；对危险/未知状态给出明确提示。
- [ ] 保持手机端操作简单，不把 PID、进程树、driver 错误等内部细节直接暴露给普通用户。

### 4. Transport 继续解耦

- [ ] 保持 Tailscale 为一种 transport，而不是核心身份/运行时模型的一部分。
- [ ] 抽象 remote transport / auth capability，为后续受限公司网络或其他接入方式留出实现边界。
- [ ] 新 transport 必须维持“Panel/ComfyUI 默认不直接暴露公网”的安全原则。

### 5. Release quality

- [ ] 将真实崩溃/恢复场景加入 v0.4 release gate。
- [ ] 保持 Windows 为主要真机验证平台，同时继续 Windows/Linux CI。
- [ ] 任何恢复功能必须优先保证“不误杀、不误重启、不伪造任务成功”。

---

## Later / separate design tracks

这些方向可以继续研究，但不自动并入 v0.4：

- Multi-host：家里 / 公司 / 其他主机的 Host Registry、selector、routing。
- Wake-on-LAN / external watchdog：依赖局域网或机外常驻设备的电源恢复。
- Seed Policy：把数字 seed 与 `randomize / fixed / increment` 等运行策略分离。
- Media optimization：高清参考图自动压缩、视频缩略图、远程预览带宽优化。
- Additional transports：在不降低安全边界的前提下补充 Tailscale 之外的连接方式。

路线图原则：**先把远程生成做稳，再扩机器数量、连接方式和电源控制。**
