from lumia_briefing_room.consent import CONSENT_ITEMS, CONSENT_VERSION, ConsentItem, needs_first_run, pending_items


def test_unanswered_config_needs_first_run():
    assert needs_first_run(0) is True
    assert [i.key for i in pending_items(0)] == [i.key for i in CONSENT_ITEMS]


def test_answered_current_version_does_not_ask_again():
    assert needs_first_run(CONSENT_VERSION) is False
    assert pending_items(CONSENT_VERSION) == []


def test_only_items_added_after_answered_version_are_asked_again():
    items = (ConsentItem("setup", 1), ConsentItem("update", 2), ConsentItem("telemetry", 3))
    assert [i.key for i in pending_items(1, items)] == ["update", "telemetry"]
    assert [i.key for i in pending_items(2, items)] == ["telemetry"]
    assert pending_items(3, items) == []
    assert needs_first_run(1, items) is True


def test_current_version_is_highest_item_version():
    assert CONSENT_VERSION == max(i.since for i in CONSENT_ITEMS)


def test_newer_answer_than_known_items_is_treated_as_answered():
    assert needs_first_run(CONSENT_VERSION + 5) is False


def test_network_items_are_asked_separately_from_setup():
    since = {i.key: i.since for i in CONSENT_ITEMS}
    assert since["setup"] == 1
    assert since["update"] == since["labels"] == since["logs"] == 2
    assert CONSENT_VERSION == 2
    assert [i.key for i in pending_items(1)] == ["update", "labels", "logs"]
