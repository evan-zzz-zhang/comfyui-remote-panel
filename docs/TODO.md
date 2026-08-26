# Comfy Remote TODO

本文档是 Comfy Remote 的执行型 TODO。当前开发基线为 **v0.3 Phase 1 — Public Readiness / 陌生 ComfyUI 部署**。

本阶段只解决公开使用门槛和陌生环境适配；生成现场恢复、视频缩略图、高清图片压缩、Windows 电源控制、WoL 与多主机明确不混入 Phase 1。

## v0.3 Phase 1 — Public Readiness

### 核心与 H3 解耦

- [x] 确认 Panel 启动不依赖 H3 模型、LoRA 或 custom node。
- [x] 内置 H3 继续作为 Bundled / Verified examples；缺依赖只影响对应工作流 availability。
- [x] 普通 ComfyUI API Workflow 继续作为一等能力。
- [ ] 陌生 Windows 实机确认“完全没有 H3 仍能导入并真实生成”。

### Public CLI

- [x] 新增 `setup`。
- [x] 新增 `start / stop / restart / status`。
- [x] 新增 `doctor / doctor --report`。
- [x] 新增 `autostart install / status / remove`。
- [x] 保留 `comfyui-remote-panel --config config.toml` 旧前台启动方式。
- [x] CLI 只负责编排，继续复用现有 app / database / workflow / lifecycle。

### Setup Wizard

- [x] 检查 Python、当前目录和已有配置。
- [x] 已有配置提供检查更新 / 新建 / 退出，写入前备份旧配置。
- [x] 优先探测运行中的 `127.0.0.1:8188`。
- [x] 限定常见位置发现 ComfyUI，不做全盘暴力扫描。
- [x] 支持手动输入标准安装或 Windows Portable 根目录。
- [x] 自动生成 base URL、input、output 与 storage 配置。
- [x] ComfyUI 启停控制单独询问并默认关闭。
- [x] 无 Tailscale 时允许先以 local auth 完成本机配置。

### Tailscale

- [x] 检测 Tailscale 可执行文件、版本、BackendState、LoginName、DNSName。
- [x] 使用当前登录身份生成 `allowed_logins`。
- [x] Setup 可确认运行 `tailscale serve --bg 8190`。
- [x] `doctor` 检查 Tailscale、身份匹配和 Serve 状态。
- [ ] 陌生 Windows + 手机真实确认 Serve 地址访问。

### Panel 进程控制

- [x] 后台启动并保存 runtime state / PID。
- [x] `status` 检查监听端口、进程命令特征和 healthz。
- [x] 发现 8190 被未知进程占用时拒绝误杀。
- [x] `stop / restart` 只操作已验证为 Comfy Remote 的进程。
- [x] 不在网页端增加“关闭 Panel”按钮。

### Windows Autostart

- [x] CLI 复用现有 Task Scheduler PowerShell 脚本，不重写任务逻辑。
- [x] Setup 在 Windows 上默认询问安装登录自启动。
- [ ] 真实执行“注销 → 登录 → 手机重新访问”验收。

### Doctor

- [x] 统一 `PASS / WARN / FAIL`。
- [x] 检查 Python、配置、data、Panel、ComfyUI API、input/output。
- [x] Tailscale 未配置或内置 H3 缺依赖按 `WARN`。
- [x] ComfyUI API 不通、关键目录不可用按 `FAIL`。
- [x] `doctor --report` 输出 GitHub Issue 可粘贴 Markdown。
- [x] 自动脱敏用户目录、邮箱、Tailscale hostname 和明显 token/secret/cookie/API key 字段。

### Workflow compatibility / Preflight

- [x] JSON 层：API Workflow JSON 与节点结构检查。
- [x] Node 层基础能力：通过当前 ComfyUI `object_info` 检查 class_type / input compatibility。
- [x] Input / Output 层基础能力：自动识别 prompt / negative / reference image / width / height / batch / output，并保留高级映射。
- [x] Runtime 层：工作流“测试”会真实提交一次 ComfyUI 任务。
- [x] 把四层结果收敛成明确的 preflight 状态对象和用户可读 PASS/WARN/FAIL 摘要。

### Windows 安装与文档

- [x] 新增 `scripts/windows/Install-ComfyRemote.ps1`。
- [x] PowerShell 只负责 Python / venv / pip / 进入 Python setup，不承载核心配置逻辑。
- [x] README 改为 setup-first Quick Start，不再把手写 TOML 当 happy path。
- [x] 新增 `docs/GETTING_STARTED_WINDOWS.md`。
- [x] 新增 `docs/TROUBLESHOOTING.md`。
- [x] 新增 `docs/PUBLIC_READINESS_ACCEPTANCE.md`。
- [x] 新增 bug / workflow compatibility / feature request Issue Forms。

### Tests / CI

- [x] CLI parsing / legacy compatibility tests。
- [x] setup config generation / Portable discovery tests。
- [x] doctor / report redaction tests。
- [x] panel stale PID / unknown port occupant safety tests。
- [x] explicit preflight tests。
- [ ] explicit minimal ComfyUI / no-H3 public-readiness test。
- [ ] 当前 PR 所有 Windows/Linux 3.11/3.13 + minimum-dependencies + repository check + build 全绿。

### Release Gate — 陌生 Windows

必须在一台没有 Comfy Remote 配置、data DB 和 H3 环境的 Windows 上，仅按公开教程走通：

- [ ] clone / download。
- [ ] `Install-ComfyRemote.ps1`。
- [ ] setup 自动或手动找到 ComfyUI。
- [ ] doctor。
- [ ] Tailscale Serve + 手机访问。
- [ ] 导出自己的 API Workflow。
- [ ] 导入 → preflight → 测试。
- [ ] 创作页真实生成。
- [ ] 任务页查看并下载结果。
- [ ] 安装 autostart。
- [ ] Windows 注销 / 重登。
- [ ] 手机再次访问。

若必须由开发者帮忙手工编辑 TOML 才能完成，Phase 1 验收失败。

## Phase 1 完成标准

- [ ] **A** 没有 H3 也能完整使用。
- [ ] **B** 普通用户 happy path 不需要理解 module / TOML / PID / Task Scheduler / LoginName / node id。
- [x] **C** 可运行 `doctor --report` 并直接提交脱敏结果。
- [ ] **D** 陌生环境普通 API Workflow 真实完成“导入 → 检查 → 生成”。
- [ ] **E** Windows 重登后 Panel 自动恢复、Serve 可访问、手机继续使用。

A / B / D / E 最终需要真机验收，不能由单元测试代替。

## Phase 1 明确不做

- 生成现场恢复增强。
- 视频缩略图专项。
- 高清参考图自动压缩。
- Windows 睡眠 / 休眠 / 系统重启 / 关机。
- Wake-on-LAN 或机外 watchdog。
- 多主机 Host Registry / routing / selector。
- Seed Policy：把种子数值与运行策略分离，支持 `randomize / fixed / increment`（可扩展 `decrement`），并允许每个工作流配置默认策略、创作页临时覆盖。API Workflow 中的数字 seed（包括 `0`）本身不作为“随机”哨兵；当前 v0.3 保持“留空随机、显式数值固定”的简单语义。

这些项目继续保留为后续版本候选，不作为 v0.3 Phase 1 阻塞项。
