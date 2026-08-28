from pathlib import Path


STATIC = Path("src/comfyui_remote_panel/static")


def _script() -> str:
    return (STATIC / "v04_ui.js").read_text(encoding="utf-8")


def test_v04_ui_does_not_install_global_dom_observers():
    script = _script()
    assert "MutationObserver" not in script
    assert "characterData" not in script


def test_v04_web_ui_temporarily_stays_chinese_only():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    script = _script()
    assert '/static/i18n.js' not in index
    assert 'id="language-toggle"' not in index
    assert "ComfyI18n" not in script


def test_v04_seed_is_recovered_for_imported_workflows_but_stays_advanced():
    script = _script()
    assert "ensureSeedMetadata" in script
    assert "seedBindingFromInspection" in script
    assert 'semantic: "seed"' in script
    assert ".v04-seed-quick" not in script
    assert "moveGenericAdvancedIntoUnifiedSection" in script
    assert "#advanced-settings" in script


def test_v04_reference_resolution_is_merged_into_advanced_settings():
    script = _script()
    assert 'document.querySelectorAll("#job-form [data-v04-resolution]")' in script
    assert 'grid.append(field)' in script
    assert "cleanResolutionCopy" in script


def test_v04_mobile_prompt_has_no_custom_keyboard_button():
    script = _script()
    assert "收起键盘" not in script
    assert "v04-keyboard-dismiss" not in script
    assert 'active?.tagName === "TEXTAREA"' in script
    assert "active.blur()" in script


def test_v04_keeps_generation_settings_done_action_and_hides_empty_generic_settings():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    script = _script()
    assert "sheet-done" not in script
    assert "syncGenerationSettingsVisibility" in script
    assert '["width", "height", "batch_size"]' in script
    assert 'section.classList.toggle("hidden", !hasEditableSetting)' in script
    assert "生成设置" in index


def test_v04_advanced_heading_uses_top_level_creation_hierarchy():
    script = _script()
    assert "v04-advanced-layout" in script
    assert "font-size: 15px" in script
    assert "font-weight: 650" in script
    assert 'title.textContent = "高级设置"' in script
