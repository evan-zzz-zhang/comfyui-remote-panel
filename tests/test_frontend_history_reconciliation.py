from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_reconciles_all_loaded_jobs_after_snapshot_and_polling():
    script = (ROOT / "src" / "comfyui_remote_panel" / "static" / "app.js").read_text(encoding="utf-8")

    assert "async function reconcileLoadedJobs()" in script
    assert "/api/jobs/existence?ids=" in script
    assert "await reconcileLoadedJobs();" in script
    assert "void reconcileLoadedJobs();" in script
    assert "slice(index, index + 100)" in script
