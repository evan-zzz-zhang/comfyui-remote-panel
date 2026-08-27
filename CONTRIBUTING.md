# Contributing / 贡献指南

Comfy Remote is currently a **v0.3 Public Beta**. Contributions should keep the project small, auditable, local-first, and safe by default.

## Development setup

Use a stable Python 3.11 or newer release. Pre-release Python builds (`alpha` / `beta` / `rc`) are not part of the supported setup path.

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

On Linux/macOS, activate/use the equivalent `.venv/bin/python` path.

## Required checks before a PR

Run:

```powershell
python -m pytest
python scripts/check_repository.py
python -m build
```

If you change frontend JavaScript, also run the same `node --check` commands used by `.github/workflows/ci.yml`.

Changes to Windows setup, lifecycle control, Tailscale integration, workflow analysis, or process management should include focused regression tests. Real GPU/custom-node behavior that cannot be represented in CI should be described explicitly in the PR.

## Project boundaries

- Do not expose ComfyUI or the Panel directly to the public Internet.
- Do not add Funnel/public-port-forward helpers.
- Do not add telemetry, analytics, advertising, or unrelated account systems.
- Do not add arbitrary remote shell/process execution.
- Do not silently rewrite a user's ComfyUI graph to make it fit the UI.
- API Workflow import is a supported core feature; changes to it must preserve Preflight, explicit mappings, revision history, and runtime safety boundaries.
- Treat third-party ComfyUI custom nodes as local trusted code; Comfy Remote does not sandbox them.
- Keep Tailscale as a transport integration rather than coupling the core workflow/runtime model to it.

## Privacy and repository hygiene

Never commit real:

- `config.toml`, databases, PID/runtime state, logs, caches;
- local absolute paths or user identities;
- Tailscale hostnames or login identities;
- API keys, tokens, cookies, passwords, or private keys;
- uploaded source media, generated media, prompts, models, LoRAs, or other user content.

Use synthetic fixtures such as `example.com` identities and temporary directories in tests. Before submitting, review `git status`, run `python scripts/check_repository.py`, and inspect the diff manually.

## Documentation

Update user-facing Chinese/English documentation whenever behavior changes. New public setup behavior should be reflected in `README.md`, `docs/GETTING_STARTED_WINDOWS.md`, or `docs/TROUBLESHOOTING.md` as appropriate.

Keep PRs focused. Explain what changed, why the change is safe, what was tested, and any known limitation that remains.
