from pathlib import Path


def test_v04_ui_does_not_install_a_second_global_dom_observer():
    script = Path("src/comfyui_remote_panel/static/v04_ui.js").read_text(encoding="utf-8")
    # i18n.js already owns the page-wide mutation observer.  A second observer
    # here caused mobile browsers to spend their main thread repeatedly walking
    # DOM updates and could freeze scrolling/navigation during startup.
    assert "MutationObserver" not in script
    assert "characterData" not in script
