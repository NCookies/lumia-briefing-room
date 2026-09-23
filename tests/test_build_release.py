import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_release  # noqa: E402


def _fake_tree(root: Path) -> Path:
    for rel in [
        "data/characters.json",
        "data/templates/digits/2560x1440.npz",
        "data/templates/regions/2560x1440.npz",
        "data/templates/days/2560x1440.npz",
        "src/lumia_briefing_room/profiles/builtin/2560x1440.json",
        "frontend/dist/index.html",
        "vendor/ffmpeg/ffmpeg.exe",
        "vendor/ffmpeg/ffprobe.exe",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    return root


def test_release_and_zip_names_come_from_the_version():
    assert build_release.release_name("0.1.0") == "LumiaBriefingRoom-0.1.0"
    assert build_release.zip_name("1.2.3") == "LumiaBriefingRoom-1.2.3-win64.zip"


def test_data_specs_cover_every_runtime_resource(tmp_path: Path):
    root = _fake_tree(tmp_path)
    specs = build_release.data_specs(root)
    destinations = {dest for _, dest in specs}

    assert "data" in destinations
    assert "lumia_briefing_room/profiles/builtin" in destinations
    assert "frontend/dist" in destinations


def test_ffmpeg_is_copied_after_the_build_not_through_add_data(tmp_path: Path):
    """datas 로 넣으면 PyInstaller 가 .dll 을 _internal 루트에도 복사해 149MB 가 중복된다."""
    root = _fake_tree(tmp_path)
    assert "vendor/ffmpeg" not in {dest for _, dest in build_release.data_specs(root)}

    out = tmp_path / "out"
    (out / "_internal").mkdir(parents=True)
    dest = build_release.copy_vendor(root, out)

    assert dest == out / "_internal" / "vendor" / "ffmpeg"
    assert (dest / "ffmpeg.exe").exists() and (dest / "ffprobe.exe").exists()


def test_copy_vendor_replaces_a_stale_copy(tmp_path: Path):
    root = _fake_tree(tmp_path)
    out = tmp_path / "out"
    stale = out / "_internal" / "vendor" / "ffmpeg"
    stale.mkdir(parents=True)
    (stale / "old.dll").write_text("old", encoding="utf-8")

    dest = build_release.copy_vendor(root, out)

    assert not (dest / "old.dll").exists()


def test_data_specs_point_at_files_that_exist(tmp_path: Path):
    root = _fake_tree(tmp_path)
    for source, _ in build_release.data_specs(root):
        assert Path(source).exists(), source


def test_prerequisites_are_satisfied_by_a_complete_tree(tmp_path: Path):
    assert build_release.missing_prerequisites(_fake_tree(tmp_path)) == []


def test_missing_ffmpeg_bundle_is_reported_with_the_fix(tmp_path: Path):
    root = _fake_tree(tmp_path)
    (root / "vendor" / "ffmpeg" / "ffmpeg.exe").unlink()

    problems = build_release.missing_prerequisites(root)

    assert len(problems) == 1
    assert "fetch_ffmpeg" in problems[0]


def test_missing_templates_are_reported(tmp_path: Path):
    root = _fake_tree(tmp_path)
    (root / "data" / "templates" / "days" / "2560x1440.npz").unlink()

    problems = build_release.missing_prerequisites(root)

    assert any("본보기" in p for p in problems)


def test_frontend_build_is_not_a_prerequisite_because_the_script_builds_it(tmp_path: Path):
    root = _fake_tree(tmp_path)
    (root / "frontend" / "dist" / "index.html").unlink()

    assert build_release.missing_prerequisites(root) == []


def test_pyinstaller_args_are_onedir_windowed_and_named(tmp_path: Path):
    root = _fake_tree(tmp_path)
    args = build_release.pyinstaller_args(root, version="0.1.0", icon=root / "icon.ico")

    assert "--onedir" in args and "--windowed" in args
    assert "--onefile" not in args
    assert args[args.index("--name") + 1] == "LumiaBriefingRoom"
    assert args[args.index("--icon") + 1] == str(root / "icon.ico")
    assert args[-1].endswith("app.py")


def test_pyinstaller_args_pass_every_data_spec(tmp_path: Path):
    root = _fake_tree(tmp_path)
    args = build_release.pyinstaller_args(root, version="0.1.0", icon=root / "icon.ico")
    passed = [args[i + 1] for i, a in enumerate(args) if a == "--add-data"]

    assert len(passed) == len(build_release.data_specs(root))
    for source, dest in build_release.data_specs(root):
        assert f"{source}{build_release.SEP}{dest}" in passed


def test_pyinstaller_args_declare_the_dynamic_imports_we_need(tmp_path: Path):
    args = build_release.pyinstaller_args(_fake_tree(tmp_path), version="0.1.0", icon=tmp_path / "i.ico")
    hidden = [args[i + 1] for i, a in enumerate(args) if a == "--hidden-import"]
    collected = [args[i + 1] for i, a in enumerate(args) if a == "--collect-data"]

    assert "pystray._win32" in hidden
    assert "rapidocr" in collected


def _complete_bundle(tmp_path: Path) -> Path:
    out = tmp_path / "LumiaBriefingRoom"
    internal = out / "_internal"
    for rel in build_release.REQUIRED_IN_BUNDLE:
        (internal / rel).parent.mkdir(parents=True, exist_ok=True)
        (internal / rel).write_text("x", encoding="utf-8")
    (out / "LumiaBriefingRoom.exe").write_text("x", encoding="utf-8")
    return out


def test_verify_bundle_accepts_a_complete_output(tmp_path: Path):
    assert build_release.verify_bundle(_complete_bundle(tmp_path)) == []


def test_verify_bundle_also_accepts_a_flat_layout(tmp_path: Path):
    """PyInstaller 6 은 _internal 아래에 두지만 옛 배치도 받아들인다."""
    out = tmp_path / "LumiaBriefingRoom"
    for rel in build_release.REQUIRED_IN_BUNDLE:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text("x", encoding="utf-8")
    (out / "LumiaBriefingRoom.exe").write_text("x", encoding="utf-8")

    assert build_release.verify_bundle(out) == []


def test_verify_bundle_reports_what_pyinstaller_dropped(tmp_path: Path):
    out = tmp_path / "LumiaBriefingRoom"
    (out / "_internal").mkdir(parents=True)
    (out / "LumiaBriefingRoom.exe").write_text("x", encoding="utf-8")

    problems = build_release.verify_bundle(out)

    assert any("characters.json" in p for p in problems)
    assert any("ffmpeg" in p for p in problems)


def test_prune_removes_only_the_listed_files(tmp_path: Path):
    out = _complete_bundle(tmp_path)
    internal = out / "_internal"
    for rel in ["rapidocr/models/PP-OCRv6_rec_small.onnx", "rapidocr/models/korean_PP-OCRv5_rec_mobile.onnx"]:
        (internal / rel).parent.mkdir(parents=True, exist_ok=True)
        (internal / rel).write_bytes(b"0" * 2048)

    removed = build_release.prune_unused(out)

    assert [name for name, _ in removed] == ["rapidocr/models/PP-OCRv6_rec_small.onnx"]
    assert not (internal / "rapidocr/models/PP-OCRv6_rec_small.onnx").exists()
    assert (internal / "rapidocr/models/korean_PP-OCRv5_rec_mobile.onnx").exists()


def test_prune_keeps_the_models_the_app_actually_opens():
    """실측으로 쓰는 것을 확인한 모델은 절대 지우지 않는다."""
    used = ["PP-OCRv6_det_small", "korean_PP-OCRv5_rec_mobile", "ch_PP-OCRv5_rec_mobile", "ch_ppocr_mobile_v2.0_cls"]
    for name in used:
        assert not any(name in target for target in build_release.PRUNE)


def test_prune_is_quiet_when_a_file_is_already_gone(tmp_path: Path):
    out = _complete_bundle(tmp_path)
    assert build_release.prune_unused(out) == []


def test_verify_bundle_reports_a_missing_executable(tmp_path: Path):
    out = tmp_path / "LumiaBriefingRoom"
    (out / "_internal").mkdir(parents=True)

    assert any(".exe" in p for p in build_release.verify_bundle(out))


def test_zip_contains_the_folder_at_its_top_level(tmp_path: Path):
    import zipfile

    out = tmp_path / "LumiaBriefingRoom"
    (out / "_internal").mkdir(parents=True)
    (out / "LumiaBriefingRoom.exe").write_text("x", encoding="utf-8")
    (out / "_internal" / "a.txt").write_text("y", encoding="utf-8")

    archive = build_release.make_zip(out, tmp_path / "out.zip")

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert "LumiaBriefingRoom/LumiaBriefingRoom.exe" in names
    assert "LumiaBriefingRoom/_internal/a.txt" in names


@pytest.mark.parametrize("step", ["frontend", "pyinstaller"])
def test_a_failing_step_stops_the_build(tmp_path: Path, monkeypatch, step):
    calls = []
    monkeypatch.setattr(build_release, "build_frontend", lambda root: calls.append("frontend"))
    monkeypatch.setattr(build_release, "run_pyinstaller", lambda *a, **k: calls.append("pyinstaller"))

    def fail(*args, **kwargs):
        calls.append(step)
        raise build_release.BuildError(f"{step} 실패")

    monkeypatch.setattr(build_release, {"frontend": "build_frontend", "pyinstaller": "run_pyinstaller"}[step], fail)
    monkeypatch.setattr(build_release, "missing_prerequisites", lambda root: [])

    assert build_release.main(["--skip-checks"]) == 1
    assert "pyinstaller" not in calls[calls.index(step) + 1 :]
