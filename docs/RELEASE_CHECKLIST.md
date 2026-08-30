# Release Checklist

This checklist is for public Comfy Remote releases. Replace `vX.Y.Z` with the actual release version and keep the release title consistent with the current project maturity, for example **Comfy Remote vX.Y.Z — Public Beta** while the project remains in Public Beta.

## 1. Release metadata

- [ ] `pyproject.toml` version matches the release.
- [ ] `src/comfyui_remote_panel/__init__.py` matches the release.
- [ ] README maturity/status is accurate.
- [ ] `CHANGELOG.md` contains the release notes and known limitations.
- [ ] Security/support version text is current.
- [ ] `docs/TODO.md` current baseline matches the completed release state.

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

Also verify the normal update path separately from the full installer path:

```text
existing healthy installation
→ git pull
→ comfyui-remote-panel restart
→ Panel loads the updated source
```

The full installer is for first installation, dependency/install-metadata changes, Setup/configuration refreshes, and environment repair; it is not the default command for every source update.

## 6. Tag and Release

After the checks above pass, replace `vX.Y.Z` with the actual version:

```powershell
git switch main
git pull
git tag -a vX.Y.Z -m "Comfy Remote vX.Y.Z — Public Beta"
git push origin vX.Y.Z
```

Create the GitHub Release from tag `vX.Y.Z` with a title consistent with the current maturity, for example:

```text
Comfy Remote vX.Y.Z — Public Beta
```

Use the matching `vX.Y.Z` section of `CHANGELOG.md` as the release-note basis.

## 7. Branch and closeout hygiene

After the release PR is merged and the release state is verified:

- [ ] Verify `main` contains the intended final content.
- [ ] Check post-merge CI when applicable.
- [ ] Delete the merged remote development/release branch unless there is a documented maintenance reason to retain it.
- [ ] Delete obsolete temporary/superseded branches that are provably unnecessary.
- [ ] Keep release tags and GitHub Releases intact.
- [ ] Run `git fetch --prune` locally when stale remote-tracking refs need cleanup.

The repository should return to `main` plus only genuinely active work branches. See [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) for the full branch lifecycle rules.

## 8. First public publication

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
