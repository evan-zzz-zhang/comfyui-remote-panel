from pathlib import Path


def test_v04_ui_does_not_install_a_second_global_dom_observer():
    script = Path("src/comfyui_remote_panel/static/v04_ui.js").read_text(encoding="utf-8")
    # i18n.js already owns the page-wide mutation observer. A second observer
    # here would duplicate dynamic DOM work on mobile browsers.
    assert "MutationObserver" not in script
    assert "characterData" not in script


def test_v04_ui_detaches_language_controls_from_legacy_i18n_observer_loop():
    script = Path("src/comfyui_remote_panel/static/v04_ui.js").read_text(encoding="utf-8")
    # The legacy i18n observer calls updateLanguageUi() after each mutation.
    # v0.4 must rename the two controls before DOMContentLoaded so those writes
    # cannot retrigger the page-wide observer forever.
    assert 'languageToggle.id = "language-toggle-v04"' in script
    assert 'languageValue.id = "language-value-v04"' in script
    assert 'document.querySelector("#language-toggle-v04")' in script
    assert 'document.querySelector("#language-value-v04")' in script
    assert "ComfyI18n?.setLanguage?." in script


def test_v04_language_ui_updates_are_idempotent():
    script = Path("src/comfyui_remote_panel/static/v04_ui.js").read_text(encoding="utf-8")
    assert "value.textContent !== valueText" in script
    assert 'toggle.getAttribute("aria-label") !== labelText' in script
