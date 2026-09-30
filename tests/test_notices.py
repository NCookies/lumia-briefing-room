from lumia_briefing_room.pipeline.notices import NoticeCenter


def test_post_lists_the_notice_and_calls_the_notifier_once():
    sent = []
    center = NoticeCenter(notifier=lambda title, message: sent.append((title, message)))
    center.post("disk_low", "여유 공간 부족", title="저장 공간")
    center.post("disk_low", "여유 공간 부족", title="저장 공간")

    assert [n["kind"] for n in center.list()] == ["disk_low"]
    assert sent == [("저장 공간", "여유 공간 부족")]


def test_a_changed_message_notifies_again_and_replaces_the_notice():
    sent = []
    center = NoticeCenter(notifier=lambda t, m: sent.append(m))
    center.post("disk_low", "12GB")
    center.post("disk_low", "9GB")

    assert [n["message"] for n in center.list()] == ["9GB"]
    assert sent == ["12GB", "9GB"]


def test_clear_removes_a_notice_and_allows_it_to_notify_again():
    sent = []
    center = NoticeCenter(notifier=lambda t, m: sent.append(m))
    center.post("disk_low", "12GB")
    center.clear("disk_low")
    assert center.list() == []
    center.post("disk_low", "12GB")
    assert sent == ["12GB", "12GB"]


def test_notifier_failure_does_not_break_posting():
    def boom(t, m):
        raise RuntimeError("tray gone")

    center = NoticeCenter(notifier=boom)
    center.post("x", "m")
    assert len(center.list()) == 1


def test_notifier_can_be_attached_later():
    center = NoticeCenter()
    center.post("x", "m")
    sent = []
    center.set_notifier(lambda t, m: sent.append(m))
    center.post("y", "n")
    assert sent == ["n"]
