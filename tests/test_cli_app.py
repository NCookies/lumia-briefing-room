"""cli/app.py 고유 동작. 자동 시작 명령·레지스트리 반영은 autostart 모듈로 옮겨져 test_autostart.py 에 있다."""


def test_selftest_command_writes_a_report_and_can_stay_quiet(tmp_path, monkeypatch):
    import argparse

    from lumia_briefing_room import selftest as selftest_module
    from lumia_briefing_room.cli import app as app_module

    opened = []
    monkeypatch.setattr(app_module, "default_log_path", lambda: tmp_path / "logs" / "app.log")
    monkeypatch.setattr(app_module.os, "startfile", lambda path: opened.append(path), raising=False)
    monkeypatch.setattr(app_module.startup, "console_logging_wanted", lambda: False)
    monkeypatch.setattr(
        selftest_module, "run_all", lambda: ([selftest_module.Check("가짜", True, "좋다")], True)
    )

    assert app_module.run_selftest_command(argparse.Namespace(quiet=True)) is True

    report = (tmp_path / "logs" / "selftest.txt").read_text(encoding="utf-8")
    assert "가짜" in report and "모두 통과" in report
    assert opened == []


def test_selftest_command_opens_the_report_when_there_is_no_console(tmp_path, monkeypatch):
    import argparse

    from lumia_briefing_room import selftest as selftest_module
    from lumia_briefing_room.cli import app as app_module

    opened = []
    monkeypatch.setattr(app_module, "default_log_path", lambda: tmp_path / "logs" / "app.log")
    monkeypatch.setattr(app_module.os, "startfile", lambda path: opened.append(path), raising=False)
    monkeypatch.setattr(app_module.startup, "console_logging_wanted", lambda: False)
    monkeypatch.setattr(
        selftest_module, "run_all", lambda: ([selftest_module.Check("가짜", False, "나쁘다")], False)
    )

    assert app_module.run_selftest_command(argparse.Namespace(quiet=False)) is False
    assert opened == [tmp_path / "logs" / "selftest.txt"]
