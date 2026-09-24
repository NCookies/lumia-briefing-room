"""오류 로그 개인정보 제거 회귀 테스트. 샘플은 실제 app.log 의 구조(트레이스백, Player.log 경로, 매치 시각)를 본뜨되
사용자 이름·닉네임은 가짜(`tester`, `테스트닉`)로 바꾼 것이다."""

import json
import re

import pytest

from lumia_briefing_room.telemetry.scrub import (
    make_fingerprint,
    scrub_entry,
    scrub_message,
    scrub_stack,
)

USERS = ["tester"]
NICKS = ["테스트닉"]


def scrub(text):
    return scrub_message(text, usernames=USERS, nicknames=NICKS)


DEV_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "P:\\lumia_briefing_room\\src\\lumia_briefing_room\\pipeline\\vod_analyze.py", line 113, in _safe_result\n'
    "    return find(video, span, next_start)\n"
    '  File "P:\\lumia_briefing_room\\tests\\test_vod_analyze.py", line 245, in broken\n'
    '    raise RuntimeError("ocr 실패")\n'
    "RuntimeError: ocr 실패"
)
FROZEN_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "C:\\Users\\tester\\AppData\\Local\\Programs\\LumiaBriefingRoom\\_internal\\lumia_briefing_room\\pipeline\\watcher.py", line 231, in run_polling\n'
    "    process(session_dir, m, rescue)\n"
    '  File "C:\\Users\\tester\\AppData\\Local\\Programs\\LumiaBriefingRoom\\_internal\\cv2\\__init__.py", line 9, in imread\n'
    "    raise OSError(path)\n"
    "OSError: D:\\Videos\\테스트닉\\clips\\a.mp4 를 열 수 없다"
)


def test_removes_the_windows_user_name_from_paths():
    text = r"Player.log 감시 시작(1.0초마다 훑는다): C:\Users\tester\AppData\LocalLow\NimbleNeuron\Eternal Return\Player.log"
    out = scrub(text)
    assert "tester" not in out and "Player.log" in out


def test_removes_user_names_that_are_not_in_the_known_list():
    out = scrub(r"열 수 없다: C:\Users\SomeoneElse\Videos\a.mp4 그리고 c:/users/Another/x.txt")
    assert "SomeoneElse" not in out and "Another" not in out


def test_removes_the_nickname_everywhere():
    assert "테스트닉" not in scrub("테스트닉 님의 결과 화면을 읽었다")
    assert "테스트닉" not in scrub(r"경로 D:\Videos\테스트닉\clips 확인")


def test_absolute_paths_keep_only_the_file_name():
    out = scrub(r"녹화 폴더를 찾을 수 없다: D:\Steam Recordings\friend_name\bg_1049590\session.mpd")
    assert "friend_name" not in out and "Steam Recordings" not in out and "session.mpd" in out


def test_posix_and_unc_paths_are_scrubbed_too():
    out = scrub("/home/tester/videos/a.mp4 그리고 \\\\NAS-of-tester\\share\\vod\\b.mp4")
    assert "tester" not in out and "NAS" not in out


def test_keeps_non_personal_diagnostic_text():
    text = "매치 2026-09-19T13:05:00+00:00 처리 실패 (1/2): 게임 1 결과 화면 판독 실패"
    assert scrub(text) == text


def test_dev_tree_traceback_keeps_package_relative_frames():
    out = scrub_stack(DEV_TRACEBACK, usernames=USERS, nicknames=NICKS)
    assert "lumia_briefing_room\\pipeline\\vod_analyze.py" in out
    assert "P:\\" not in out and "RuntimeError: ocr 실패" in out


def test_frozen_traceback_drops_the_install_path_and_user_name():
    out = scrub_stack(FROZEN_TRACEBACK, usernames=USERS, nicknames=NICKS)
    assert "tester" not in out and "AppData" not in out and "테스트닉" not in out
    assert "lumia_briefing_room\\pipeline\\watcher.py" in out and "line 231, in run_polling" in out
    assert "cv2\\__init__.py" in out


def test_stack_is_capped_at_the_contract_limit_keeping_the_tail():
    long_stack = "x" * 20000 + "\nValueError: the important end"
    out = scrub_stack(long_stack, usernames=[], nicknames=[])
    assert len(out) <= 8000 and out.endswith("the important end")


def test_message_is_capped_at_the_contract_limit():
    assert len(scrub("가" * 5000)) <= 2000


def test_blank_names_do_not_break_anything():
    assert scrub_message("plain text", usernames=["", " ", None], nicknames=[None, ""]) == "plain text"


def test_short_user_names_only_match_inside_paths():
    out = scrub_message(r"a 는 alice 보다 작다 C:\Users\al\Videos\a.mp4", usernames=["al"], nicknames=[])
    assert "alice" in out and "\\al\\" not in out


def entry(**over):
    base = {
        "ts": "2026-09-24T01:47:36", "level": "ERROR", "logger": "lumia_briefing_room.pipeline.watcher",
        "message": "매치 2026-09-19T13:05:00+00:00 처리 실패 (1/2)", "exceptionType": "RuntimeError",
        "stack": FROZEN_TRACEBACK,
    }
    base.update(over)
    return base


def test_scrub_entry_scrubs_message_and_stack_and_adds_a_fingerprint():
    out = scrub_entry(entry(message=r"C:\Users\tester\a.mp4 테스트닉"), usernames=USERS, nicknames=NICKS)
    dumped = json.dumps(out, ensure_ascii=False)
    assert "tester" not in dumped and "테스트닉" not in dumped
    assert re.fullmatch(r"[0-9a-f]{16}", out["fingerprint"])
    assert set(out) <= {"ts", "level", "logger", "message", "exceptionType", "stack", "fingerprint"}


def test_entry_without_an_exception_omits_exception_fields():
    out = scrub_entry({"ts": "t", "level": "ERROR", "logger": "x", "message": "m"}, usernames=[], nicknames=[])
    assert "exceptionType" not in out and "stack" not in out


def test_fingerprint_ignores_line_numbers_and_volatile_numbers_but_not_the_location():
    a = make_fingerprint("lg", "RuntimeError", 'File "x\\a.py", line 10, in f\n', "처리 실패 1")
    b = make_fingerprint("lg", "RuntimeError", 'File "x\\a.py", line 99, in f\n', "처리 실패 2")
    c = make_fingerprint("lg", "RuntimeError", 'File "x\\a.py", line 10, in g\n', "처리 실패 1")
    assert a == b and a != c


def test_fingerprint_for_plain_messages_groups_by_normalized_text():
    a = make_fingerprint("lg", None, None, "게임 1 결과 화면 판독 실패 2026-09-19T13:05:00")
    b = make_fingerprint("lg", None, None, "게임 7 결과 화면 판독 실패 2026-10-01T09:00:00")
    assert a == b


@pytest.mark.parametrize("value", [None, 5, ["x"]])
def test_non_string_values_do_not_crash(value):
    assert isinstance(scrub_message(value, usernames=[], nicknames=[]), str)
