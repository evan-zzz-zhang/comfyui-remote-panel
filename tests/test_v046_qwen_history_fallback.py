from types import SimpleNamespace

from comfyui_remote_panel import v046 as v046_module
from comfyui_remote_panel.preset import load_presets


PRESET_ID = "h3-fl2va-v4step600-qwen35-4b"


def service():
    return SimpleNamespace(presets=load_presets())


def test_qwen_history_prefers_save_node_standardized_prompt_metadata():
    entry = {
        "outputs": {
            "92": {
                "videos": [],
                "metadata": {"standardized_prompt": "metadata prompt"},
            },
            "177": {"text": ["preview fallback prompt"]},
        }
    }

    assert v046_module._qwen_standardized_prompt(
        service(), {"preset_id": PRESET_ID}, entry
    ) == "metadata prompt"


def test_qwen_history_falls_back_to_previewany_final_prompt():
    preset = service().presets[PRESET_ID]
    assert preset.template["177"]["class_type"] == "PreviewAny"
    assert preset.template["177"]["inputs"]["source"] == ["176", 0]

    entry = {
        "outputs": {
            "92": {"videos": [{"filename": "result.mp4"}]},
            "177": {"text": ["Qwen3.5 standardized H3 prompt"]},
        }
    }

    assert v046_module._qwen_standardized_prompt(
        service(), {"preset_id": PRESET_ID}, entry
    ) == "Qwen3.5 standardized H3 prompt"


def test_qwen_history_does_not_invent_prompt_when_neither_history_source_has_text():
    entry = {"outputs": {"92": {"videos": []}, "177": {}}}

    assert v046_module._qwen_standardized_prompt(
        service(), {"preset_id": PRESET_ID}, entry
    ) is None
