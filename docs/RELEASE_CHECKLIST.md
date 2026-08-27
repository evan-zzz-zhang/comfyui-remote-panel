# Release Checklist

This checklist is for public Comfy Remote releases. For `v0.3.0`, the release title is **Comfy Remote v0.3.0 — Public Beta**.

## 1. Release metadata

- [ ] `pyproject.toml` version matches the release.
- [ ] `src/comfyui_remote_panel/__init__.py` matches the release.
- [ ] README maturity/status is accurate.
- [ ] `CHANGELOG.md` contains the release notes and known limitations.
- [ ] Security/support version text is current.

## 2. Repository privacy / hygiene

Run from a full local clone:

```powershell
python scripts/check_repository.py
python scripts/check_history.py
```

For the first transition from private to public, also review commit author/committer metadata:

```powershell
python scripts/check_history.py --strict-metadata
```

`--strict-metadata` intentionally fails if reachable commits contain non-noreply email metadata. A Git author email is not automatically a secret, but it becomes public metadata when the repository becomes public. Decide explicitly whether that is acceptable. If it is not acceptable, rewrite history **before** tagging/publication; history rewriting changes commit SHAs and must not be done casually after releases are published.

Also manually confirm that the repository does not contain real:

- `config.toml`, `.env`, database, PID/runtime files, or logs;
- absolute machine/user paths;
- Tailscale hostname/login identity;
- API keys, tokens, cookies, passwords, private keys;
- uploaded/generated media, model weights, LoRAs, or prompt history.

## 3. Local automated checks

Use a stable supported Python:

```powershell
python -m pytest
python scripts/check_repository.py
python scripts/check_history.py
python -m build
```

Frontend syntax checks must also pass (see `.github/workflows/ci.yml`).

## 4. GitHub Actions

The exact release commit must have real executed jobs for:

- Windows / Python 3.11;
- Windows / Python 3.13;
- Linux / Python 3.11;
- Linux / Python 3.13;
- minimum dependencies;
- repository/history safety.

A workflow run with zero steps / no runner logs is infrastructure failure, not green CI.

## 5. Final smoke test

Use a clean clone of the final `main` candidate:

```text
clone final main
→ Install-ComfyRemote.ps1
→ setup
→ doctor
→ start/status
→ phone access
→ import one ordinary API Workflow
→ one real generation
→ result visible on phone
```

This is intentionally smaller than a full development acceptance matrix.

## 6. Tag and Release

After the checks above pass:

```powershell
git switch main
git pull
git tag -a v0.3.0 -m "Comfy Remote v0.3.0 — Public Beta"
git push origin v0.3.0
```

Create the GitHub Release from tag `v0.3.0` with title:

```text
Comfy Remote v0.3.0 — Public Beta
```

Use the `v0.3.0` section of `CHANGELOG.md` as the release-note basis.

## 7. First public publication

For the first public release only, change repository visibility **after** release prep and deliberate privacy review.

GitHub UI:

```text
Repository
→ Settings
→ General
→ Danger Zone
→ Change repository visibility
→ Change visibility
→ Public
```

Read GitHub's confirmation carefully before completing the change. After the repository is public, immediately open the README as a logged-out/incognito visitor and verify the Quick Start, docs links, Issues, tag, and Release are visible as intended.
