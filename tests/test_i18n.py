from pathlib import Path

from comfyui_remote_panel.locale import (
    normalize_language,
    translate_cli,
    translate_multiline,
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


def test_v04_web_panel_temporarily_disables_dynamic_i18n_for_mobile_stability() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="language-toggle"' not in index
    assert 'id="language-value"' not in index
    assert '/static/i18n.js' not in index
    assert '<html lang="zh-CN">' in index


def test_web_dictionary_still_covers_core_and_configurator_surfaces_for_future_reenablement() -> None:
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


def test_doctor_multiline_translation_is_readable_in_simplified_chinese() -> None:
    source = "\n".join(
        [
            "Core",
            "PASS data directory — <PATH> (writable)",
            "ComfyUI",
            "PASS API — reachable; version 0.3.50",
            "Remote access",
            "WARN Remote auth — local auth mode; remote access is not configured",
            "Workflow compatibility",
            "PASS demo — output=image; required inputs=none; missing nodes=none; warnings=none",
            "Overall",
            "READY",
        ]
    )
    translated = translate_multiline(source, "zh-CN")
    assert "核心" in translated
    assert "数据目录" in translated
    assert "可访问；版本 0.3.50" in translated
    assert "远程认证 — 本地认证模式；未配置远程访问" in translated
    assert "输出=image; 必需输入=无; 缺失节点=无; 警告=无" in translated
    assert translated.endswith("就绪")
    assert "un可用" not in translated
