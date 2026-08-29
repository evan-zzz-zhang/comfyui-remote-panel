from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def test_recovery_lite_frontend_is_explicit_and_observer_free():
    script = (STATIC / "recovery_lite.js").read_text(encoding="utf-8")
    assert "MutationObserver" not in script
    assert 'data-recovery-control="force_restart"' in script
    assert "/api/comfyui/control/force_restart" in script
    assert "强制重启会结束已安全确认的 ComfyUI 进程及其子进程" in script
    assert "REMOTE PANEL" in script
    assert 'unresponsive: "无响应"' in script


def test_recovery_lite_does_not_reintroduce_arbitrary_process_control():
    script = (STATIC / "recovery_lite.js").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "comfyui_remote_panel" / "recovery_lite.py").read_text(encoding="utf-8")
    assert "taskkill" not in script.lower()
    assert "taskkill" not in backend.lower()
    assert "python.exe" not in script.lower()
    assert 'request.path == "/static/app.js"' in backend
    assert "application.middlewares.append(recovery_lite_asset)" in backend


def test_ci_checks_recovery_lite_javascript_syntax():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node --check src/comfyui_remote_panel/static/recovery_lite.js" in workflow
