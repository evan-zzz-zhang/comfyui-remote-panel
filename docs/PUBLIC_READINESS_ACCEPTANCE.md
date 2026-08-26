# v0.3 Phase 1 Public Readiness Acceptance

本清单是 v0.3 Phase 1 的 Release Gate。CI 不能替代最后的陌生 Windows 真机验收。

## 自动化 Gate

- [ ] Python 3.11 / 3.13：Windows + Linux pytest 全绿。
- [ ] `scripts/check_repository.py` 全绿。
- [ ] wheel build 全绿。
- [ ] CLI smoke tests 覆盖旧启动方式与新子命令解析。
- [ ] setup config generation tests。
- [ ] doctor / redaction tests。
- [ ] panel PID/未知端口占用保护 tests。
- [ ] 没有 H3 模型/节点时，Panel 仍可启动并使用普通 API Workflow。

## 陌生 Windows 条件

测试电脑必须：

- 从未安装过 Comfy Remote。
- 没有开发机的 `config.toml`。
- 没有开发机的 data DB。
- 不要求存在 H3 环境。
- 本机 ComfyUI 原本能运行。
- 至少有一个简单图片 API Workflow 可用于测试。

开发者不得帮测试者手工改 TOML。

## 必须完整走通

- [ ] clone / download。
- [ ] `Install-ComfyRemote.ps1`。
- [ ] `setup`。
- [ ] 自动或手动找到 ComfyUI。
- [ ] `doctor`。
- [ ] Tailscale Serve。
- [ ] 手机访问。
- [ ] 从 ComfyUI 导出 API Workflow。
- [ ] 导入并检查映射/兼容性。
- [ ] 真实测试。
- [ ] 创作页生成。
- [ ] 任务页查看结果。
- [ ] 下载结果。
- [ ] 启用 autostart。
- [ ] Windows 注销并重新登录。
- [ ] 手机再次访问。

若必须手工编辑 TOML 才能完成，Phase 1 验收失败。

## 完成标准 A–E

### A — H3 可选

没有 H3 模型、LoRA 或 custom node 仍能启动 Panel、打开 UI、导入自己的 Workflow 并生成。

### B — Happy path 不暴露内部概念

普通用户不需要理解 Python module、TOML、PID、Task Scheduler、Tailscale LoginName 或 ComfyUI node id。

### C — 可诊断

出现问题可以运行：

```powershell
comfyui-remote-panel doctor --report
```

并直接把脱敏结果提交 Issue。

### D — 普通 API Workflow

自己的 ComfyUI API Workflow 可以完成：

```text
导入 → 检查 → 测试 → 生成
```

### E — 登录恢复

Windows 注销/重登后：

```text
Panel 自动回来
Tailscale Serve 可访问
手机继续能用
```
