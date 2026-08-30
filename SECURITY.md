# Security Policy / 安全策略

## Supported version

Security fixes are provided for the latest released version. The currently supported public-beta release line is **0.4.x**; older release lines may not receive backported fixes.

## Deployment boundary

- Bind the panel only to `127.0.0.1` and keep ComfyUI 8188 local.
- Use Tailscale Serve for the supported remote-access path; never use Funnel, public port forwarding, or a public reverse proxy for the panel.
- Restrict both Tailscale access control and `allowed_logins` to the intended user.
- Treat other processes running on the workstation as trusted: a local process can connect to localhost and forge proxy headers.
- Do not install unreviewed workflow packages or dangerous custom nodes.
- A third-party ComfyUI custom node runs with the permissions of the local ComfyUI process. Comfy Remote does not sandbox custom nodes.

The panel rejects cross-origin browser writes, unrecognized identity headers, oversized or unsafe images, untracked output paths, recursive deletion, and global ComfyUI interruption. Imported API Workflows are analyzed and preflighted before use, but runtime behavior still depends on the local ComfyUI installation and its custom nodes.

## Reporting

Run `comfyui-remote-panel doctor --report` before reporting a problem when possible.

Do **not** open a public issue containing real identities, local absolute paths, prompts, uploaded images/video/audio, generated media, `config.toml`, database files, full logs, Tailscale hostnames, API keys, tokens, cookies, or other secrets. The Doctor report performs automatic redaction, but review it before posting.

For a security-sensitive report, contact the repository owner privately with the smallest reproducible example and sanitized diagnostics.

## 中文摘要

安全修复以最新公开版本为准；当前 Public Beta 支持线为 **0.4.x**，旧版本线不保证回补安全修复。

面板与 ComfyUI 应只监听本机，通过 Tailscale Serve 访问，不得启用 Funnel 或公网端口映射。第三方 ComfyUI Custom Node 仍属于本机代码执行边界，Comfy Remote 不会对它们进行沙箱隔离。

公开反馈前优先运行 `doctor --report`，并再次检查输出。不要在公开 Issue 中上传身份、真实本机路径、提示词、素材、生成结果、配置文件、数据库、完整日志、Tailscale 主机名或任何密钥/token。
