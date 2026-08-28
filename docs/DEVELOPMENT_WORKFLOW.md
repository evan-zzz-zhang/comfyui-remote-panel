# Development Workflow / 开发与收尾流程

This document defines the branch lifecycle and closeout procedure for Comfy Remote. It applies to human contributors and AI coding agents.

## 1. Branch lifecycle

Use focused branches for active work. Typical prefixes:

- `feat/` — product features
- `fix/` — bug fixes
- `release/` — release preparation
- `chore/` — repository maintenance
- `i18n/` — localization work

Before starting substantial work, update from the intended base and verify that the branch is not stale.

The desired steady state is intentionally small:

```text
main
active feature/fix branch(es)
```

Merged branches are historical implementation vehicles, not permanent records. Commits, merged PRs, tags, and GitHub Releases preserve history after branch deletion.

## 2. Definition of Done for a PR

A PR is ready to merge only when all applicable items are complete:

- Implementation matches the agreed scope.
- Tests cover changed behavior.
- CI is green, or an infrastructure blocker is explicitly documented.
- Required Windows/GPU/mobile/Tailscale/custom-node real-machine acceptance is complete when CI cannot represent the behavior.
- Temporary debug code, trigger files, local fixtures, generated artifacts, and experimental scaffolding are removed.
- Repository safety/privacy checks pass.
- Public behavior changes are reflected in both English and Simplified Chinese documentation.
- Known limitations and intentionally deferred work are documented rather than silently omitted.

## 3. Documentation synchronization

Before merge, review every documentation surface affected by the change instead of updating only the code.

Check as applicable:

- `README.md`
- `README.zh-CN.md`
- `docs/TODO.md`
- `CHANGELOG.md`
- `docs/GETTING_STARTED_WINDOWS.md`
- `docs/GETTING_STARTED_WINDOWS.zh-CN.md`
- `docs/TROUBLESHOOTING.md`
- `docs/TROUBLESHOOTING.zh-CN.md`
- `docs/WORKFLOWS.md`
- `docs/WORKFLOWS.zh-CN.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- package version metadata
- GitHub Release notes / Known Limitations

Rules:

- Completed work must not remain shown as an open TODO.
- The current development baseline in `docs/TODO.md` must match the branch/release actually being developed.
- Version strings in code, CLI/UI, docs, tag, and Release must not contradict each other.
- When a public behavior exists in both English and Chinese documentation, update both sides in the same closeout.

## 4. Required validation before merge

Run the repository checks relevant to the change. The default baseline is:

```powershell
python -m pytest
python scripts/check_repository.py
python -m build
```

For frontend changes, also run the JavaScript syntax/i18n checks used by `.github/workflows/ci.yml`.

For release work, additionally check the full public-release gates defined by the current roadmap/release checklist.

## 5. "Merge and close out" checklist

When the owner requests "merge and close out" / "合并并收尾", execute this sequence as one operation.

### Before merge

- [ ] Confirm branch and PR are the intended ones.
- [ ] Confirm no unrelated or accidental files are included.
- [ ] Confirm tests/CI/acceptance status.
- [ ] Remove temporary/debug/test-trigger artifacts.
- [ ] Synchronize documentation.
- [ ] Update TODO / roadmap state.
- [ ] Update changelog/version/release metadata when applicable.

### Merge

- [ ] Merge the PR to the intended base.
- [ ] Verify the target branch contains the expected final commit/content.

### After merge

- [ ] Check post-merge CI when applicable.
- [ ] Verify rendered README/docs/release metadata if the change is public-facing.
- [ ] Delete the merged remote branch.
- [ ] Delete obsolete temporary/superseded branches that are now provably unnecessary.
- [ ] Keep tags and Releases intact.
- [ ] Ask the local developer to run `git fetch --prune` only when local stale remote-tracking refs need cleanup.

## 6. Safe branch deletion rules

A branch may normally be deleted when one of these is true:

- its PR has been merged and the work is present in the target branch;
- it is fully behind the retained branch with `ahead = 0`;
- its only unique commit is a known disposable test/debug trigger;
- its unique content has been intentionally superseded and reviewed.

Do **not** delete a branch when:

- it is the current active development branch;
- it contains unique implementation work whose disposition is unclear;
- it is needed for an open PR;
- deletion would be used to hide unresolved work rather than close it out.

Before deleting a suspicious unmerged branch, compare it against `main` or the retained branch and inspect the unique files/commits.

## 7. Release branch policy

Release branches are temporary. After the release PR is merged and the tag/GitHub Release exists:

- keep the tag;
- keep the GitHub Release;
- delete the release branch unless a specific maintenance reason is documented.

Do not keep old `release/vX.Y.Z` branches merely as historical markers.

## 8. Final closeout report

A closeout response must state the final condition, not just that the PR was merged.

Use a compact report such as:

```text
PR: merged
Target branch: verified
CI / acceptance: PASS
Docs / TODO / changelog: synchronized
Version / Release: checked
Merged remote branch: deleted
Other obsolete branches: deleted / none
Remaining active branches: main + <active branch>
Local action: none / git fetch --prune
```

If any item cannot be completed because of permissions or tool limitations, say so explicitly. Do not label the closeout complete until the blocker is resolved or the owner knowingly accepts the remaining manual step.

## 9. Current project expectation

The repository should normally return to a clean branch list after each milestone. Branch accumulation is treated as unfinished closeout work, not as harmless history.
