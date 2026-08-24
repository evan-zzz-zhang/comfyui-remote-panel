# Security Policy / 安全策略

## Supported version

Security fixes are provided for the latest 0.1.x release.

## Deployment boundary

- Bind the panel only to `127.0.0.1` and keep ComfyUI 8188 local.
- Use Tailscale Serve, never Funnel, public port forwarding, or a public reverse proxy.
- Restrict both Tailscale access control and `allowed_logins` to the intended user.
- Treat other processes running on the workstation as trusted: a local process can connect to localhost and forge proxy headers.
- Do not install unreviewed workflow presets or dangerous custom nodes.

The panel rejects arbitrary workflow graphs, cross-origin browser writes, unrecognized identity headers, oversized or unsafe images, untracked output paths, recursive deletion, and global ComfyUI interruption.

## Reporting

Do not open a public issue containing identities, paths, prompts, images, logs, database files, or generated media. Contact the repository owner privately with a minimal reproduction and sanitized logs.

## 中文摘要

面板与 ComfyUI 必须只监听本机，通过 Tailscale Serve 访问，不得启用 Funnel 或公网端口映射。不要在公开 Issue 中上传身份、路径、提示词、媒体、数据库或完整日志。

