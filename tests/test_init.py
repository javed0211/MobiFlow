from pathlib import Path

from mobiflow.config import (
    DeviceConfig,
    LlmConfig,
    MobiflowConfig,
    ProjectConfig,
    RunConfig,
    StackConfig,
)
from mobiflow.init import _ensure_project_docs
from mobiflow.samples import bundled_case_names, copy_sample_library, sample_library_root


REPO = Path(__file__).resolve().parents[1]
PKG_SAMPLES = REPO / "src" / "mobiflow" / "samples"


def _config(tmp_path: Path, *, app_id: str = "", platform: str = "android") -> MobiflowConfig:
    return MobiflowConfig(
        project=ProjectConfig(path=str(tmp_path)),
        llm=LlmConfig(),
        stack=StackConfig(language="yaml+js", scripts_dir="flows/scripts"),
        device=DeviceConfig(platform=platform, app_id=app_id),
        run=RunConfig(),
    )


def test_packaged_samples_cover_repo_cases():
    repo_cases = sorted(p.name for p in (REPO / "cases").glob("*.txt"))
    pkg_cases = sorted(p.name for p in (PKG_SAMPLES / "cases").glob("*.txt"))
    assert repo_cases
    assert pkg_cases == repo_cases
    assert "android_browserstack_smoke.txt" in pkg_cases
    assert "android_testmu_smoke.txt" in pkg_cases
    assert "android_e2e_api_hooks.txt" in pkg_cases


def test_sample_library_includes_companion_flows_and_data():
    root = sample_library_root()
    assert (root / "flows" / "android_browserstack_smoke.yaml").is_file()
    assert (root / "flows" / "scripts" / "e2e_seed.js").is_file()
    assert (root / "data" / "example.json").is_file()


def test_init_seeds_all_sample_cases(tmp_path: Path):
    cfg = _config(tmp_path)
    _ensure_project_docs(tmp_path, cfg)

    names = bundled_case_names()
    written = sorted(p.name for p in (tmp_path / "cases").glob("*.txt"))
    assert written == names
    assert (tmp_path / "cases" / "example.txt").is_file()
    assert (tmp_path / "cases" / "android_joplin_smoke.txt").is_file()
    assert (tmp_path / "cases" / "android_bitwarden_smoke.txt").is_file()
    assert (tmp_path / "cases" / "android_e2e_api_hooks.txt").is_file()
    assert (tmp_path / "cases" / "android_browserstack_smoke.txt").is_file()
    assert (tmp_path / "cases" / "android_testmu_smoke.txt").is_file()
    assert (tmp_path / "cases" / "ios_gesture_logic_lab.txt").is_file()
    assert (tmp_path / "flows" / "android_e2e_api_hooks.yaml").is_file()
    assert (tmp_path / "flows" / "scripts" / "e2e_seed.js").is_file()
    assert (tmp_path / "flows" / "scripts" / "helpers.js").is_file()
    assert (tmp_path / "data" / "example.json").is_file()
    assert (tmp_path / "cases" / "README.md").is_file()


def test_init_patches_new_example_app_id(tmp_path: Path):
    cfg = _config(tmp_path, app_id="com.example.app", platform="ios")
    _ensure_project_docs(tmp_path, cfg)
    text = (tmp_path / "cases" / "example.txt").read_text(encoding="utf-8")
    assert "com.example.app" in text
    assert "platform: ios" in text


def test_init_does_not_overwrite_existing_case(tmp_path: Path):
    dest = tmp_path / "cases"
    dest.mkdir(parents=True)
    custom = dest / "example.txt"
    custom.write_text("task: Keep me\n", encoding="utf-8")
    _ensure_project_docs(tmp_path, _config(tmp_path, app_id="com.example.app"))
    assert custom.read_text(encoding="utf-8") == "task: Keep me\n"
    # Other starters still land beside the custom file
    assert (dest / "android_testmu_smoke.txt").is_file()


def test_copy_sample_library_skips_existing(tmp_path: Path):
    first = copy_sample_library(tmp_path)
    assert first
    second = copy_sample_library(tmp_path)
    assert second == []
