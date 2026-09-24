from pathlib import Path

from lumia_briefing_room import selftest


def _by_name(results):
    return {r.name: r for r in results}


def test_check_records_ok_and_detail():
    result = selftest.Check("본보기", True, "3개")
    assert (result.name, result.ok, result.detail) == ("본보기", True, "3개")


def test_resource_checks_pass_in_the_source_tree():
    results = _by_name(selftest.check_resources())
    assert results["캐릭터 이름표"].ok is True
    assert results["K/A 숫자 본보기"].ok is True
    assert results["지역명 본보기"].ok is True
    assert results["일차 본보기"].ok is True


def test_resource_checks_fail_loudly_when_the_bundle_is_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    results = _by_name(selftest.check_resources())

    assert results["캐릭터 이름표"].ok is False
    assert results["K/A 숫자 본보기"].ok is False
    assert str(tmp_path) in results["캐릭터 이름표"].detail


def test_frontend_check_reports_missing_build(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    result = _by_name(selftest.check_resources())["열람 UI (frontend/dist)"]
    assert result.ok is False
    assert "npm run build" in result.detail


def test_ffmpeg_check_reports_the_path_it_found(tmp_path: Path, monkeypatch):
    resource = tmp_path / "res"
    bundled = resource / "vendor" / "ffmpeg"
    bundled.mkdir(parents=True)
    (bundled / "ffmpeg.exe").write_bytes(b"")
    (bundled / "ffprobe.exe").write_bytes(b"")
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(resource))
    monkeypatch.delenv("LUMIA_FFMPEG", raising=False)

    results = _by_name(selftest.check_tools())

    assert results["ffmpeg"].ok is True and "vendor" in results["ffmpeg"].detail
    assert results["ffprobe"].ok is True


def test_ffmpeg_check_fails_when_nothing_is_found(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    monkeypatch.delenv("LUMIA_FFMPEG", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    results = _by_name(selftest.check_tools())
    assert results["ffmpeg"].ok is False
    assert results["H.264 프록시 인코더"].ok is False


def test_encoder_check_lists_the_usable_encoders(monkeypatch):
    monkeypatch.setattr(selftest, "discover_ffmpeg", lambda: Path("ffmpeg"))
    monkeypatch.setattr(selftest, "list_encoders", lambda ffmpeg: {"h264_mf", "libx264", "hevc_nvenc"})

    result = _by_name(selftest.check_tools())["H.264 프록시 인코더"]

    assert result.ok is True
    assert "h264_mf" in result.detail and "hevc_nvenc" not in result.detail


def test_report_marks_failures_and_counts_them():
    results = [selftest.Check("가", True, "좋다"), selftest.Check("나", False, "나쁘다")]
    text = selftest.format_report(results, header="루미아")

    assert "루미아" in text
    assert "[ OK ] 가" in text and "[실패] 나" in text
    assert "1개 실패" in text


def test_report_says_all_clear_when_nothing_failed():
    text = selftest.format_report([selftest.Check("가", True, "")], header="x")
    assert "모두 통과" in text


def test_all_checks_returns_results_and_a_failure_flag(monkeypatch):
    monkeypatch.setattr(selftest, "check_ocr", lambda: [selftest.Check("OCR", False, "안 됨")])
    results, ok = selftest.run_all()
    assert ok is False
    assert any(r.name == "OCR" for r in results)
    assert any(r.name == "실행 환경" for r in results)


def test_environment_check_reports_frozen_state_and_version():
    result = _by_name(selftest.check_environment())["실행 환경"]
    from lumia_briefing_room import __version__

    assert __version__ in result.detail
    assert "개발" in result.detail


def test_ocr_check_really_loads_the_engine():
    """PyInstaller 로 묶었을 때 rapidocr 모델·onnxruntime 누락을 잡는 검사다."""
    results = _by_name(selftest.check_ocr())
    assert results["결과 화면 OCR"].ok is True, results["결과 화면 OCR"].detail


def test_telemetry_checks_pass_in_the_source_tree_and_report_the_token_state(monkeypatch):
    from lumia_briefing_room.telemetry import endpoint

    monkeypatch.setattr(endpoint, "bundled_endpoint", lambda: {})
    results = {c.name: c for c in selftest.check_telemetry()}
    assert results["전송 클라이언트(httpx·인증서)"].ok and results["개인정보 처리 안내"].ok
    assert results["서버 연결 정보"].ok and "꺼져" in results["서버 연결 정보"].detail
    monkeypatch.setattr(endpoint, "bundled_endpoint", lambda: {"token": "t"})
    assert "들어 있다" in {c.name: c for c in selftest.check_telemetry()}["서버 연결 정보"].detail


def test_missing_privacy_document_fails_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(selftest.paths, "resource_dir", lambda: tmp_path)
    results = {c.name: c for c in selftest.check_telemetry()}
    assert results["개인정보 처리 안내"].ok is False
