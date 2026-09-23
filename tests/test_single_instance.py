import sys
import threading
import uuid

import pytest

from lumia_briefing_room.single_instance import SingleInstance

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 이름 있는 뮤텍스 전용")


@pytest.fixture
def name():
    return f"LumiaBriefingRoomTest_{uuid.uuid4().hex[:8]}"


def test_first_acquires_second_is_refused(name):
    first, second = SingleInstance(name), SingleInstance(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.close()
        first.close()


def test_released_after_close_can_be_acquired_again(name):
    first = SingleInstance(name)
    assert first.acquire() is True
    first.close()
    again = SingleInstance(name)
    try:
        assert again.acquire() is True
    finally:
        again.close()


def test_different_names_do_not_conflict(name):
    a, b = SingleInstance(name + "a"), SingleInstance(name + "b")
    try:
        assert a.acquire() is True
        assert b.acquire() is True
    finally:
        a.close()
        b.close()


def test_second_instance_can_ask_first_to_open_ui(name):
    first, second = SingleInstance(name), SingleInstance(name)
    opened = threading.Event()
    try:
        assert first.acquire() is True
        first.listen(opened.set)
        assert second.acquire() is False
        assert second.signal_existing() is True
        assert opened.wait(3)
    finally:
        second.close()
        first.close()


def test_signal_without_running_instance_reports_failure(name):
    lonely = SingleInstance(name)
    try:
        assert lonely.signal_existing() is False
    finally:
        lonely.close()
