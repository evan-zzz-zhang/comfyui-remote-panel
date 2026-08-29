# AGENTS.md

This file defines repository-wide instructions for AI coding agents and automated development assistants working on Comfy Remote.

## Scope

These rules apply to the entire repository unless a more specific nested `AGENTS.md` overrides them.

## Project principles

- Keep Comfy Remote local-first, auditable, and safe by default.
- Do not expose ComfyUI or the Panel directly to the public Internet.
- Do not add arbitrary remote shell/process execution.
- Keep Tailscale as a transport integration rather than coupling core workflow/runtime logic to it.
- Do not silently rewrite a user's ComfyUI workflow graph to make it fit the UI.
- Preserve generic ComfyUI API Workflow support and H3 optionality.
- Never commit real credentials, identities, local paths, runtime databases, logs, uploaded media, generated media, models, LoRAs, or other user content.

## Before making changes

- Read `docs/TODO.md` to confirm the current development baseline.
- Read `CONTRIBUTING.md` and `docs/DEVELOPMENT_WORKFLOW.md` before creating or merging a PR.
- Work from the latest intended base branch. Do not start substantial work from a stale branch.
- Keep each branch focused on one feature, fix, release, or maintenance task.
- Add or update tests for behavior changes.
- Update both English and Simplified Chinese public documentation when user-facing behavior changes.

## Required validation

Before a PR is considered ready, run the relevant repository checks, normally including:

```text
python -m pytest
python scripts/check_repository.py
python -m build
```

Also run frontend syntax/i18n checks when frontend code changes, matching `.github/workflows/ci.yml`.

Real GPU, Windows lifecycle, Tailscale, custom-node, or mobile behavior that cannot be represented in CI must be explicitly covered by real-machine acceptance or clearly documented as unverified.

## "Merge and close out" is a complete lifecycle operation

When the project owner asks to "merge and close out", "合并并收尾", or equivalent wording, merging the PR is only one step. The task is not complete until the full closeout checklist has been performed.

Required closeout steps:

1. Confirm the PR scope matches the implemented changes.
2. Confirm required tests, CI, and any real-machine acceptance are complete.
3. Remove temporary/debug/test-trigger files and development-only artifacts.
4. Synchronize documentation affected by the change, including as applicable:
   - `README.md`
   - `README.zh-CN.md`
   - `docs/TODO.md`
   - `CHANGELOG.md`
   - setup/troubleshooting/workflow/security/contributing docs
   - version/release metadata
5. Mark completed TODO items as completed and move the active development baseline forward when appropriate.
6. Merge the PR into its intended base branch.
7. Verify the target branch contains the merged work and check post-merge CI when applicable.
8. Delete the merged remote feature/fix/release branch unless there is a documented reason to keep it.
9. Remove obsolete temporary or superseded branches discovered during closeout.
10. Preserve tags and releases; branch deletion must not be used as a substitute for release history.
11. Report the final repository state clearly: merged PR, CI/acceptance status, documentation status, release/version status, deleted branches, and remaining active branches.

Do not report "closeout complete" while an obsolete merged branch still remains, unless branch deletion is blocked by tooling or permissions. In that case, state the blocker explicitly and provide the exact minimal manual command/action required.

## Branch hygiene

The normal steady state should be small:

- `main`
- currently active development branch(es)

Merged feature/fix/release branches should be deleted promptly. Historical work should remain discoverable through commits, merged PRs, tags, and Releases rather than permanent stale branches.

Before deleting any unmerged branch, verify whether it contains commits not represented on `main` or another retained branch. Never delete an active branch or a branch with unique work without explicit review.

## Detailed workflow

See `docs/DEVELOPMENT_WORKFLOW.md` for the full branch lifecycle, Definition of Done, merge closeout checklist, documentation synchronization rules, and cleanup procedure.
