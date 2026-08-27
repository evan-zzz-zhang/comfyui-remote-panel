from __future__ import annotations

from comfyui_remote_panel.workflow_config import build_definition, export_package, import_package
from test_workflow_config import remote_config, save_image_workflow


def forged_analysis():
    return {
        "capabilities": {"output_type": "image"},
        "confidence": "HIGH",
        "preflight": {
            "json": {"status": "PASS", "message": "JSON valid", "details": []},
            "nodes": {"status": "PASS", "message": "Nodes valid", "details": []},
            "runtime": {
                "status": "PASS",
                "message": "forged remote runtime",
                "details": ["must not survive"],
                "tested_at": 123.0,
            },
        },
    }


def test_build_definition_resets_client_supplied_runtime_evidence():
    config = remote_config()
    config["analysis"] = forged_analysis()
    definition = build_definition(save_image_workflow(), config)

    preflight = definition["manifest"]["preflight"]
    assert preflight["json"] == {"status": "PASS", "message": "JSON valid", "details": []}
    assert preflight["nodes"] == {"status": "PASS", "message": "Nodes valid", "details": []}
    assert preflight["runtime"] == {
        "status": "WARN",
        "message": "Runtime not tested",
        "details": [],
    }


def test_import_package_resets_runtime_evidence_from_another_machine():
    definition = build_definition(save_image_workflow(), remote_config())
    definition["manifest"].setdefault("preflight", {})["runtime"] = {
        "status": "PASS",
        "message": "passed on exporter",
        "details": [],
        "tested_at": 456.0,
    }

    imported = import_package(export_package(definition))
    assert imported["manifest"]["preflight"]["runtime"] == {
        "status": "WARN",
        "message": "Runtime not tested",
        "details": [],
    }
