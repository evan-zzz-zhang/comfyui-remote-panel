from pathlib import Path


def _script() -> str:
    return Path("src/comfyui_remote_panel/static/v04_ui.js").read_text(encoding="utf-8")


def test_v04_ui_does_not_install_a_second_dom_observer():
    script = _script()
    assert "new MutationObserver" not in script


def test_v04_temporarily_disables_page_wide_i18n_observer():
    script = _script()
    assert 'localStorage.setItem("comfy-remote-language", "zh-CN")' in script
    assert 'window.ComfyI18n?.setLanguage?.("zh-CN")' in script
    assert "legacyPageWideObserver" in script
    assert 'document.querySelector("#language-toggle")?.remove()' in script


def test_v04_seed_is_recovered_and_exposed_for_imported_workflows():
    script = _script()
    assert "ensureSeedMetadata" in script
    assert "seedBindingFromInspection" in script
    assert 'semantic: "seed"' in script
    assert 'className = "creation-section v04-seed-quick"' in script


def test_v04_mobile_creation_copy_is_simplified():
    script = _script()
    assert "cleanResolutionCopy" in script
    assert "工作流决定|跟随源图|跟随输入图" in script
    assert 'done.textContent = "关闭"' in script
    assert 'button.textContent = "收起键盘"' in script


def test_v04_hides_empty_generic_generation_settings():
    script = _script()
    assert "syncGenerationSettingsVisibility" in script
    assert '["width", "height", "batch_size"]' in script
    assert 'section.classList.toggle("hidden", !hasEditableSetting)' in script
