# Contributing / 贡献指南

Keep changes small, auditable, and inside the panel repository. Do not add arbitrary workflow upload, model download, telemetry, analytics, account systems, public exposure helpers, or global ComfyUI queue controls.

Before opening a pull request:

1. Run the complete test suite on Python 3.11 or later.
2. Run `python scripts/check_repository.py`.
3. Confirm that no local configuration, identity, absolute path, media, database, log, model, or prompt history is included.
4. Update Chinese and English documentation for user-visible behavior.

Preset contributions are deferred to the v0.2 manifest validation workflow. For v0.1, changes to the bundled graph must include graph-structure tests and an explanation of every unlocked field.

