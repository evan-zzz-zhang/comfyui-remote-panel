from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_repository import _privacy_findings  # noqa: E402


def test_doctor_redaction_fixture_paths_are_not_repository_privacy_failures():
    synthetic = "G:" + "\\AI\\ComfyUI_H3_Portable\\ComfyUI\\input"
    assert _privacy_findings("tests/test_doctor.py", synthetic) == []


def test_historical_doctor_bare_drive_assertion_is_allowed_without_hiding_real_path():
    historical_source = 'assert "' + "G:" + "\\\\" + '" not in report'
    assert _privacy_findings("tests/test_doctor.py", historical_source) == []

    real_machine_path = "G:" + "\\Private\\ComfyUI\\config.toml"
    findings = _privacy_findings("tests/test_doctor.py", real_machine_path)
    assert "Windows absolute path: tests/test_doctor.py" in findings


def test_historical_scanner_self_comment_is_allowed_without_hiding_real_path():
    historical_source = "fake " + "G:" + "\\" + " drive prefix"
    assert _privacy_findings("scripts/check_repository.py", historical_source) == []

    real_machine_path = "G:" + "\\Private\\ComfyUI\\config.toml"
    findings = _privacy_findings("scripts/check_repository.py", real_machine_path)
    assert "Windows absolute path: scripts/check_repository.py" in findings


def test_documented_bilingual_windows_path_placeholders_are_allowed():
    chinese = "D:" + "\\你的目录\\ComfyUI_windows_portable"
    english = "D:" + "\\your-folder\\ComfyUI_windows_portable"
    assert _privacy_findings("docs/GETTING_STARTED_WINDOWS.zh-CN.md", chinese) == []
    assert _privacy_findings("docs/GETTING_STARTED_WINDOWS.md", english) == []


def test_real_machine_path_is_still_rejected_in_other_source_file():
    machine_path = "D:" + "\\Private\\ComfyUI\\config.toml"
    findings = _privacy_findings("README.md", machine_path)
    assert "Windows absolute path: README.md" in findings


def test_historical_scanner_tailscale_marker_is_allowed_but_real_host_is_not():
    historical_marker = "tail123" + ".ts.net"
    assert _privacy_findings("scripts/check_repository.py", historical_marker) == []

    real_host = "my-private-machine" + ".tail999.ts.net"
    findings = _privacy_findings("README.md", real_host)
    assert "non-placeholder Tailscale hostname: README.md" in findings
