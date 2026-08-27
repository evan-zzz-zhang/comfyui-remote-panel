from pathlib import Path

from comfyui_remote_panel.locale import (
    normalize_language,
    translate_cli,
    translated_input,
)


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def test_public_docs_have_english_and_simplified_chinese_entry_points() -> None:
    pairs = [
        (ROOT / "README.md", ROOT / "README.zh-CN.md"),
        (ROOT / "docs" / "GETTING_STARTED_WINDOWS.md", ROOT / "docs" / "GETTING_STARTED_WINDOWS.zh-CN.md"),
        (ROOT / "docs" / "TROUBLESHOOTING.md", ROOT / "docs" / "TROUBLESHOOTING.zh-CN.md"),
        (ROOT / "docs" / "WORKFLOWS.md", ROOT / "docs" / "WORKFLOWS.zh-CN.md"),
    ]
    for english, chinese in pairs:
        assert english.is_file()
        assert chinese.is_file()
        assert "简体中文" in english.read_text(encoding="utf-8")
        assert "English" in chinese.read_text(encoding="utf-8")


def test_web_panel_loads_i18n_before_feature_scripts_and_exposes_language_switch() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")

    assert 'id="language-toggle"' in index
    assert 'id="language-value"' in index
    assert index.index('/static/i18n.js') < index.index('/static/app.js')
    assert 'localStorage.setItem(STORAGE_KEY' in i18n
    assert 'navigator.language' in i18n
    assert 'document.documentElement.lang = currentLanguage' in i18n
    assert 'MutationObserver' in i18n
    assert 'window.ComfyI18n' in i18n


def test_web_panel_dictionary_covers_core_and_configurator_surfaces() -> None:
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
    for source in (
        "创作",
        "任务",
        "设备",
        "生成设置",
        "管理工作流",
        "导入 API Workflow",
        "选择手机端可修改参数",
        "高级设置",
        "再次生成",
        "查看结果",
        "工作站在线",
    ):
        assert f'"{source}"' in i18n


def test_cli_language_normalization_and_setup_prompt_translation() -> None:
    assert normalize_language("zh_CN") == "zh-CN"
    assert normalize_language("en-US") == "en"
    assert translate_cli("Comfy Remote 已启动", "en") == "Comfy Remote started"
    assert translate_cli("选择操作", "en") == "Choose action"

    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "y"

    wrapped = translated_input(fake_input, "en")
    assert wrapped("允许 Comfy Remote 启动、关闭和重启 ComfyUI [y/N]: ") == "y"
    assert prompts == ["Allow Comfy Remote to start, stop, and restart ComfyUI [y/N]: "]
