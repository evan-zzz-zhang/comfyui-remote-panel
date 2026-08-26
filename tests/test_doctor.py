from comfyui_remote_panel.doctor import DoctorCheck, FAIL, PASS, WARN, format_markdown, redact_text


def test_doctor_report_redacts_user_paths_email_tailscale_and_secret():
    windows_user_path = "C:" + "\\Users\\" + "Alice\\ComfyUI"
    source = (
        windows_user_path
        + " owner@example.com machine.tail123.ts.net token=super-secret"
    )
    redacted = redact_text(source)
    assert "Alice" not in redacted
    assert "owner@example.com" not in redacted
    assert "machine.tail123.ts.net" not in redacted
    assert "super-secret" not in redacted
    assert "<USER_PATH>" in redacted
    assert "o***@example.com" in redacted
    assert "<TAILSCALE_HOST>.ts.net" in redacted
    assert "<REDACTED>" in redacted


def test_markdown_report_uses_only_public_severity_levels():
    report = format_markdown(
        [
            DoctorCheck("Core", "Python", PASS, "3.13"),
            DoctorCheck("Remote access", "Tailscale", WARN, "not installed"),
            DoctorCheck("ComfyUI", "API", FAIL, "offline"),
        ]
    )
    assert "**PASS**" in report
    assert "**WARN**" in report
    assert "**FAIL**" in report
    assert "NOT READY" in report
