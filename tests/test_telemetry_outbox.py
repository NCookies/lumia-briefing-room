import json
import logging
import threading

from lumia_briefing_room.logsetup import setup_file_logging
from lumia_briefing_room.telemetry.outbox import Outbox, OutboxHandler, entry_from_record


def make_logger(name, outbox_path, **kw):
    logger = logging.getLogger(name)
    logger.handlers = []
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    handler = OutboxHandler(Outbox(outbox_path, **kw))
    logger.addHandler(handler)
    return logger, handler


def test_errors_are_recorded_with_logger_exception_type_and_stack(tmp_path):
    logger, _ = make_logger("lumia_briefing_room.test.a", tmp_path / "errors.jsonl")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.exception("처리 실패 (1/2)")
    (entry,) = Outbox(tmp_path / "errors.jsonl").read()
    assert entry["level"] == "ERROR" and entry["logger"] == "lumia_briefing_room.test.a"
    assert entry["message"] == "처리 실패 (1/2)" and entry["exceptionType"] == "RuntimeError"
    assert "Traceback" in entry["stack"] and "RuntimeError: boom" in entry["stack"]
    assert entry["ts"]


def test_only_error_and_above_are_recorded(tmp_path):
    logger, _ = make_logger("lumia_briefing_room.test.b", tmp_path / "errors.jsonl")
    logger.info("info")
    logger.warning("warn")
    logger.error("err")
    logger.critical("crit")
    assert [e["level"] for e in Outbox(tmp_path / "errors.jsonl").read()] == ["ERROR", "CRITICAL"]


def test_read_skips_corrupt_lines_and_missing_file(tmp_path):
    box = Outbox(tmp_path / "e.jsonl")
    assert box.read() == []
    (tmp_path / "e.jsonl").write_text('{"message": "ok", "level": "ERROR"}\nnot json\n\n[1]\n', encoding="utf-8")
    assert [e["message"] for e in box.read()] == ["ok"]


def test_discard_removes_only_the_first_n_entries(tmp_path):
    box = Outbox(tmp_path / "e.jsonl")
    for i in range(5):
        box.append({"message": f"m{i}", "level": "ERROR"})
    box.discard_first(3)
    assert [e["message"] for e in box.read()] == ["m3", "m4"]
    box.discard_first(10)
    assert box.read() == []


def test_cap_drops_the_oldest_entries_first(tmp_path):
    box = Outbox(tmp_path / "e.jsonl", max_bytes=2000)
    for i in range(100):
        box.append({"message": f"message number {i:03d}", "level": "ERROR"})
    entries = box.read()
    assert (tmp_path / "e.jsonl").stat().st_size <= 2000 + 200
    assert entries[-1]["message"] == "message number 099" and entries[0]["message"] != "message number 000"


def test_append_never_raises_even_when_the_path_is_unwritable(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    Outbox(blocker / "sub" / "e.jsonl").append({"message": "m"})


def test_concurrent_appends_and_discards_do_not_corrupt_the_file(tmp_path):
    box = Outbox(tmp_path / "e.jsonl")

    def writer():
        for i in range(50):
            box.append({"message": f"m{i}", "level": "ERROR"})

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    box.discard_first(1)
    for t in threads:
        t.join()
    lines = (tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line) for line in lines) and len(lines) >= 199


def test_entry_message_and_stack_are_bounded(tmp_path):
    logger, _ = make_logger("lumia_briefing_room.test.c", tmp_path / "e.jsonl")
    logger.error("x" * 100_000)
    (entry,) = Outbox(tmp_path / "e.jsonl").read()
    assert len(entry["message"]) <= 12_000


def test_entry_from_record_handles_records_without_exception():
    record = logging.LogRecord("n", logging.ERROR, "f", 1, "hello %s", ("w",), None)
    entry = entry_from_record(record)
    assert entry["message"] == "hello w" and "exceptionType" not in entry


def test_setup_file_logging_twice_does_not_duplicate_lines(tmp_path):
    path = tmp_path / "logs" / "app.log"
    setup_file_logging(path)
    setup_file_logging(path)
    logging.getLogger("lumia_briefing_room.dupcheck").warning("once")
    text = path.read_text(encoding="utf-8")
    assert text.count("once") == 1
