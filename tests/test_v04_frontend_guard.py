from pathlib import Path


STATIC = Path("src/comfyui_remote_panel/static")


def _script() -> str:
    return (STATIC / "v04_ui.js").read_text(encoding="utf-8")


def _configurator_script() -> str:
    return (STATIC / "configurator_v2.js").read_text(encoding="utf-8")


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


def test_v04_explicitly_splits_specialized_and_generic_rendering():
    script = _script()
    assert 'return preset?.family === "generic" ? "generic" : "specialized"' in script
    assert "renderSpecializedAdvanced" in script
    assert "renderGenericAdvanced" in script
    assert 'if (workflowKind(preset) === "generic")' in script
    assert "moveGenericAdvancedIntoUnifiedSection" not in script
    assert "baseAdvancedFields" not in script
    assert "v04-hidden-for-generic" not in script


def test_v04_generic_advanced_requires_and_recovers_real_workflow_bindings():
    script = _script()
    assert "function parameterSpec" in script
    assert "preset?.input_bindings?.values?.[id]" in script
    assert "manifest?.parameters?.[id]" in script
    assert "function parameterEntries" in script
    assert "function hasRealBinding" in script
    assert "spec?.node != null && Boolean(spec?.input)" in script
    assert "parameterEntries(preset).filter" in script
    assert 'data-workflow-node=' in script
    assert 'data-workflow-input=' in script


def test_v04_seed_is_recovered_for_imported_workflows_but_stays_advanced():
    script = _script()
    assert "ensureSeedMetadata" in script
    assert "seedBindingFromInspection" in script
    assert 'semantic: "seed"' in script
    assert ".v04-seed-quick" not in script
    assert 'policyField.innerHTML = `<span>种子策略</span>' in script
    assert 'grid.append(policyField)' in script


def test_v04_reference_resolution_is_inside_generic_advanced_settings():
    script = _script()
    assert 'const label = visibleSpecs.length === 1 ? "参考图分辨率"' in script
    assert 'field.className = "field v04-resolution"' in script
    assert "grid.append(field)" in script
    assert 'data-generic-binding="media_resolution"' in script


def test_v04_mobile_prompt_uses_stable_native_focus_without_custom_button():
    script = _script()
    assert "收起键盘" not in script
    assert "v04-keyboard-dismiss" not in script
    assert "function neutralizePromptContainers" in script
    assert 'label.prompt-field, label.semantic-prompt' in script
    assert 'document.body.classList.remove("prompt-focused")' in script
    assert '.classList.add("prompt-focused")' not in script
    assert "min-height: 132px" in script
    assert "resize: none" in script
    assert 'active?.tagName === "TEXTAREA"' in script
    assert "active.blur()" in script


def test_v04_generation_settings_have_persistent_preset_owned_generic_guard():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    script = _script()
    assert "sheet-done" not in script
    assert 'const GENERATION_SETTING_IDS = ["width", "height", "batch_size"]' in script
    assert "function genericGenerationSettingIds" in script
    assert "hasRealBinding(parameterSpec(preset, id, publicSpec))" in script
    assert 'form.dataset.v04GenerationSettings = hasEditableSetting ? "available" : "none"' in script
    assert '#job-form[data-v04-generation-settings="none"] #basic-settings' in script
    assert '#basic-settings.v04-generic-settings-unavailable' in script
    assert 'section.classList.toggle("v04-generic-settings-unavailable", !hasEditableSetting)' in script
    assert 'section.classList.toggle("hidden", !hasEditableSetting)' in script
    assert 'button.disabled = !hasEditableSetting' in script
    assert 'syncGenerationSettingsVisibility();\n    queueCreationUx(overrides);' in script
    assert 'form?.addEventListener("change", () => {' in script
    assert 'window.requestAnimationFrame(() => syncGenerationSettingsVisibility())' in script
    assert "MutationObserver" not in script
    assert "生成设置" in index


def test_configurator_read_only_profile_cannot_reopen_generation_settings():
    script = _configurator_script()
    start = script.index("function updateGenericProfileSummary")
    end = script.index("function bindGenericMediaDetails", start)
    block = script[start:end]
    assert "read-only" in block
    assert "#basic-settings" not in block
    assert "settings-chip" not in block
    assert 'classList.remove("hidden")' not in block


def test_v04_advanced_heading_uses_same_top_level_hierarchy_for_both_paths():
    script = _script()
    assert "v04-specialized-advanced" in script
    assert "v04-generic-advanced" in script
    assert "font-size: 15px" in script
    assert "font-weight: 650" in script
    assert '<summary><span>高级设置</span>' in script
