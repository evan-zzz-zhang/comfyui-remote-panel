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

## Baseline lock before implementation

For every non-trivial change, inspect the current implementation before editing it. Do not infer behavior from filenames, old plans, or assumptions when the current code can be read.

Before implementation, identify and preserve:

- the current user-visible behavior;
- the authoritative data source for each affected value;
- the backend-to-frontend data flow;
- the current Specialized / Generic workflow boundary;
- storage ownership and cleanup behavior when files are involved;
- accepted mobile interaction behavior when the creation UI is involved;
- the smallest set of files that should reasonably need modification.

The implementation plan must explicitly state:

- what is in scope;
- what is out of scope;
- which existing behaviors are protected invariants;
- which UI areas must remain visually and behaviorally unchanged;
- which APIs/data contracts are being changed, if any;
- what regression scenarios must pass before the phase is complete.

Do not begin by refactoring a neighboring subsystem merely because it appears cleaner. If a requested change can be implemented without changing an existing contract, prefer that path.

## Minimal-change discipline

- Make the smallest coherent change that satisfies the agreed requirement.
- Do not perform unrelated cleanup, renaming, formatting sweeps, architecture rewrites, or dependency changes in the same task unless explicitly approved.
- Do not add extra buttons, help text, labels, cards, settings, animations, status messages, or explanatory UI that were not requested.
- Do not change existing defaults unless the requested behavior requires it.
- Do not change a stable API response shape merely to make frontend implementation easier when an additive field or dedicated endpoint is sufficient.
- Do not mutate the repository to probe tool capabilities. Capability discovery must be read-only. Never create temporary branches, placeholder files, commits, tags, or other repository objects merely to test whether an action is available.

An accepted UI is treated as a protected interface. Existing layout, hierarchy, icons, SVG paths, labels, spacing, mobile focus behavior, and control visibility must remain unchanged unless the task explicitly requires a change to that exact element.

## Frontend and UI regression protection

Frontend changes require special caution because small DOM/CSS changes can affect unrelated workflows and mobile behavior.

- Do not replace, move, wrap, or recreate existing DOM nodes unless necessary for the requested behavior.
- Do not rewrite existing SVG markup or icon paths unless the icon itself is the requested change.
- Do not introduce global DOM scanning, broad `MutationObserver` behavior, or document-wide event interception when an explicit renderer/state update can solve the problem.
- Do not duplicate renderers, observers, event listeners, or state synchronization loops.
- Preserve native textarea focus/blur and mobile keyboard behavior unless the task explicitly targets it.
- Preserve the existing Settings navigation/open/close behavior.
- Preserve Panel / ComfyUI device-state rendering when unrelated UI work is performed.
- Preserve current Web i18n behavior/state unless localization is explicitly in scope.

When creation UI code changes, regression coverage must consider at least the affected combinations of:

- Specialized workflow;
- Generic workflow;
- txt2img;
- img2img / reference-image workflow;
- workflow switching in both directions;
- workflow with and without width/height/batch bindings;
- Seed controls where supported and absence of Seed controls where unsupported;
- mobile prompt interaction;
- existing advanced-parameter bindings.

A change that works for one workflow but breaks another is not complete.

## Data-contract discipline

Before using a frontend or backend field, determine where its authoritative value actually lives.

- Do not assume public preset metadata contains private/internal workflow bindings.
- Do not duplicate a source of truth when an authoritative manifest, database record, binding map, or runtime record already exists.
- Keep workflow capability, editable parameter, runtime state, stored job input, and generated artifact metadata conceptually separate.
- Prefer additive, backward-compatible schema changes.
- Database migrations must consider existing installations and rollback/older-code compatibility where practical.
- File reuse, deletion, purge, retry, and history behavior must be designed together so that a new optimization cannot orphan files or delete files still referenced by another job.

When a feature crosses layers, document the complete path before coding, for example:

```text
Database / FileStore
→ JobService
→ HTTP API
→ frontend state
→ renderer / DOM
```

Do not implement the last layer first and guess the missing contracts afterward.

## Phase-by-phase development rule

For multi-step work, complete and verify one phase before expanding the scope.

Each phase should follow this sequence:

```text
inspect current behavior
→ define invariant and contract
→ implement smallest change
→ add focused tests
→ run relevant regression tests
→ inspect git diff / git status
→ confirm no unrelated change
→ proceed to next phase
```

Do not accumulate several partially verified UI/backend changes and defer all integration testing until the end.

If a phase uncovers an architectural assumption that contradicts the current code, stop and revise the plan before continuing instead of layering compatibility patches on top of the wrong assumption.

## Diff scope audit

Before every commit that changes product behavior, inspect the complete diff and working tree.

At minimum verify:

- every modified file is necessary for the current phase;
- no accepted UI element changed unintentionally;
- no unrelated text, icon, SVG path, CSS rule, default, or setting changed;
- no temporary/debug/placeholder file is present;
- no generated file, local artifact, media file, database, log, PID, or environment-specific content is staged;
- no duplicate event listener, observer, renderer, compatibility shim, or state path was accidentally introduced;
- tests added for a fix fail against the broken behavior and protect the intended invariant rather than only matching implementation text.

If the reason for a changed line cannot be explained in terms of the current requirement, revert it before committing.

Avoid meaningless commits such as `temp`, placeholder commits, or commits whose only purpose is to probe tooling. Development history should remain reviewable.

## Regression-first bug fixing

When fixing a regression or low-level mistake:

1. identify the exact invariant that was broken;
2. add or update a regression test for that invariant when feasible;
3. apply the narrowest fix;
4. rerun tests for both the failing scenario and adjacent workflows/states;
5. inspect the diff for collateral UI or contract changes.

Do not repeatedly patch visible symptoms when the underlying state/data-source assumption is wrong.

## Required validation

Before a PR is considered ready, run the relevant repository checks, normally including:

```text
python -m pytest
python scripts/check_repository.py
python -m build
```

Also run frontend syntax/i18n checks when frontend code changes, matching `.github/workflows/ci.yml`.

Real GPU, Windows lifecycle, Tailscale, custom-node, or mobile behavior that cannot be represented in CI must be explicitly covered by real-machine acceptance or clearly documented as unverified.

For user-visible creation changes, automated tests are necessary but not sufficient when mobile/native-browser behavior is involved. Keep real-device acceptance focused on a predefined matrix rather than discovering basic regressions ad hoc after implementation.

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
