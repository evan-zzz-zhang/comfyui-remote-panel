import asyncio
from pathlib import Path

import pytest
from PIL import Image

from comfyui_remote_panel.db import Database
from comfyui_remote_panel.image_resolution import process_image, target_size
from comfyui_remote_panel.jobs import JobService
from comfyui_remote_panel.v04 import _classify_error, _media_resolution_for_role
from comfyui_remote_panel.workflow_analysis import analyze_workflow


def base_record(job_id: str, **overrides):
    record = {
        "id": job_id,
        "preset_id": "workflow",
        "workflow_id": "workflow",
        "status": "submitting",
        "mode": "test",
        "prompt": "test",
        "duration_seconds": 5,
        "aspect_ratio": "1:1",
        "megapixels": 1.0,
        "scheduler": "normal",
        "sampler": "euler",
        "steps": 8,
        "input_values": {},
    }
    record.update(overrides)
    return record


def test_target_size_24mp_to_about_1mp_without_crop():
    width, height = target_size(6000, 4000, 1.0)
    assert width * height <= 1_000_000
    assert width * height >= 990_000
    assert abs(width / height - 1.5) < 0.003
    assert (width, height) == (1224, 816)


@pytest.mark.parametrize("size", [(1600, 900), (900, 1600), (1200, 1200)])
def test_resize_preserves_aspect_ratio_for_common_shapes(tmp_path, size):
    path = tmp_path / "source.png"
    Image.new("RGB", size, "white").save(path)
    meta = process_image(path, policy="auto", target_megapixels=0.5)
    assert meta["source_width"] == size[0]
    assert meta["source_height"] == size[1]
    assert meta["effective_width"] * meta["effective_height"] <= 500_000
    assert abs(
        meta["effective_width"] / meta["effective_height"] - size[0] / size[1]
    ) < 0.003
    with Image.open(path) as resized:
        assert resized.size == (meta["effective_width"], meta["effective_height"])


@pytest.mark.parametrize(
    ("suffix", "image_format"),
    [(".jpg", "JPEG"), (".png", "PNG"), (".webp", "WEBP")],
)
def test_resize_preserves_supported_file_format(tmp_path, suffix, image_format):
    path = tmp_path / f"source{suffix}"
    Image.new("RGB", (1200, 800), "white").save(path, format=image_format)
    meta = process_image(path, policy="auto", target_megapixels=0.5)
    assert meta["resized"] is True
    with Image.open(path) as resized:
        assert resized.format == image_format
        assert resized.width * resized.height <= 500_000


def test_resize_does_not_upscale_and_original_is_unchanged(tmp_path):
    small = tmp_path / "small.png"
    Image.new("RGB", (640, 480), "white").save(small)
    before = small.read_bytes()
    auto = process_image(small, policy="auto", target_megapixels=1.0)
    assert (auto["effective_width"], auto["effective_height"]) == (640, 480)
    assert auto["resized"] is False
    assert small.read_bytes() == before

    original = tmp_path / "original.jpg"
    Image.new("RGB", (1600, 900), "white").save(original, format="JPEG")
    before = original.read_bytes()
    meta = process_image(original, policy="original")
    assert (meta["effective_width"], meta["effective_height"]) == (1600, 900)
    assert meta["resized"] is False
    assert original.read_bytes() == before


def test_auto_applies_exif_orientation_safely(tmp_path):
    path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (400, 800), "white")
    exif = image.getexif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)

    meta = process_image(path, policy="auto", target_megapixels=1.0)
    assert (meta["source_width"], meta["source_height"]) == (800, 400)
    assert meta["orientation_applied"] is True
    with Image.open(path) as result:
        assert result.size == (800, 400)
        assert result.getexif().get(274, 1) == 1


@pytest.mark.asyncio
async def test_fixed_seed_zero_is_a_real_seed(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    record = base_record(
        "fixed-zero",
        seed_policy="fixed",
        seed_value="0",
        _has_seed=True,
        _seed_min=0,
        _seed_max=999,
    )
    await db.create_job(record, [])
    job = await db.get_job("fixed-zero")
    assert job["seed_policy"] == "fixed"
    assert job["seed_value"] == "0"
    assert job["actual_seed"] == "0"
    assert job["seed"] == "0"
    assert job["input_values"]["seed"] == "0"


@pytest.mark.asyncio
async def test_increment_seed_is_atomic_under_concurrent_creation(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()

    async def create(index: int):
        record = base_record(
            f"increment-{index}",
            seed_policy="increment",
            seed_value="100",
            _has_seed=True,
            _seed_min=0,
            _seed_max=999,
        )
        await db.create_job(record, [])
        return await db.get_job(record["id"])

    jobs = await asyncio.gather(*(create(index) for index in range(10)))
    actual = sorted(int(job["actual_seed"]) for job in jobs)
    assert actual == list(range(100, 110))
    assert all(job["seed_policy"] == "increment" for job in jobs)
    assert all(job["seed_value"] == "100" for job in jobs)


@pytest.mark.asyncio
async def test_randomize_persists_actual_seed(monkeypatch, tmp_path):
    import comfyui_remote_panel.v04 as v04

    monkeypatch.setattr(v04.secrets, "randbelow", lambda _: 7)
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    record = base_record(
        "random",
        seed_policy="randomize",
        seed_value=None,
        _has_seed=True,
        _seed_min=10,
        _seed_max=99,
    )
    await db.create_job(record, [])
    job = await db.get_job("random")
    assert job["seed_policy"] == "randomize"
    assert job["seed_value"] is None
    assert job["actual_seed"] == "17"
    assert job["input_values"]["seed"] == "17"


@pytest.mark.asyncio
async def test_again_inherits_increment_policy_and_base_seed(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    record = base_record(
        "finished",
        status="succeeded",
        seed_policy="increment",
        seed_value="100",
        _has_seed=True,
        _seed_min=0,
        _seed_max=999,
        media_metadata={
            "image_0": {
                "resolution_policy": "auto",
                "target_megapixels": 1.0,
                "source_width": 3000,
                "source_height": 2000,
                "effective_width": 1224,
                "effective_height": 816,
            }
        },
    )
    await db.create_job(record, [])

    service = object.__new__(JobService)
    service.db = db
    service.files = type("Files", (), {"role_kind": staticmethod(lambda _: None)})()
    draft = await service.retry("finished")

    assert draft["seed_policy"] == "increment"
    assert draft["seed_value"] == "100"
    assert draft["actual_seed"] == "100"
    assert draft["seed"] == "100"
    assert draft["media_resolution"]["image_0"] == {
        "policy": "auto",
        "target_megapixels": 1.0,
    }


def test_shared_image_resolution_override_applies_to_frame_pair_roles():
    preset = type("Preset", (), {
        "media_binding": {
            "type": "frame_pair",
            "roles": {"first": {}, "last": {}},
            "resolution_defaults": {
                "first": {"resolution_policy": "auto", "target_megapixels": 1.0, "allow_auto": True},
                "last": {"resolution_policy": "auto", "target_megapixels": 1.0, "allow_auto": True},
            },
        }
    })()
    settings = _media_resolution_for_role(
        preset,
        "first",
        {"image": {"policy": "auto", "target_megapixels": 0.5}},
    )
    assert settings["resolution_policy"] == "auto"
    assert settings["target_megapixels"] == 0.5


def test_workflow_analysis_protects_control_and_unknown_image_inputs():
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
        "2": {"class_type": "ControlNetApply", "inputs": {"image": ["1", 0]}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "test"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "unknown.png"}},
    }
    result = analyze_workflow(workflow).to_dict()
    by_node = {item["node"]: item for item in result["media_inputs"] if item["kind"] == "image"}
    assert by_node["1"]["resolution_policy"] == "original"
    assert by_node["1"]["allow_auto"] is False
    assert by_node["4"]["resolution_policy"] == "original"
    assert by_node["4"]["allow_auto"] is False


def test_workflow_analysis_marks_img2img_as_configurable_but_conservative():
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "source.png"}},
        "2": {"class_type": "VAEEncode", "inputs": {"pixels": ["1", 0]}},
        "3": {"class_type": "KSampler", "inputs": {"latent_image": ["2", 0], "seed": 0}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "test"}},
    }
    result = analyze_workflow(workflow).to_dict()
    source = next(item for item in result["media_inputs"] if item["node"] == "1")
    assert source["semantic"] == "source_image"
    assert source["resolution_policy"] == "original"
    assert source["allow_auto"] is True
    assert "生成尺寸" in source["resolution_note"]


@pytest.mark.parametrize(
    ("job", "category"),
    [
        ({"status": "failed", "error_summary": "CUDA out of memory"}, "cuda_oom"),
        ({"status": "failed", "error_summary": "checkpoint model not found"}, "missing_model"),
        ({"status": "failed", "error_summary": "custom node missing"}, "missing_node"),
        ({"status": "failed", "error_code": "output_missing"}, "output_missing"),
        ({"status": "submitting", "error_code": "submission_uncertain"}, "comfyui_disconnected"),
        ({"status": "interrupted"}, "interrupted"),
        ({"status": "failed", "error_summary": "some third-party failure"}, "runtime_error"),
    ],
)
def test_error_categories(job, category):
    assert _classify_error(job) == category
