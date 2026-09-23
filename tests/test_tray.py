from lumia_briefing_room.tray import build_icon, build_menu, default_icon_image


def test_default_icon_image_has_requested_size():
    img = default_icon_image(48)
    assert img.size == (48, 48)
    assert img.mode == "RGBA"


def test_build_menu_has_expected_items_in_order():
    menu = build_menu(
        on_open=lambda: None,
        on_toggle_watch=lambda: None,
        watch_enabled=lambda: False,
        on_quit=lambda: None,
    )
    items = list(menu)
    assert len(items) == 4  # 열기, 감시중, 구분선, 종료
    assert items[0].text == "루미아 브리핑룸 열기"
    assert items[1].text == "감시 중"
    assert items[3].text == "종료"


def test_open_item_triggers_callback():
    calls = []
    menu = build_menu(
        on_open=lambda: calls.append("open"),
        on_toggle_watch=lambda: None,
        watch_enabled=lambda: False,
        on_quit=lambda: None,
    )
    open_item = list(menu)[0]
    open_item(None)  # pystray.MenuItem.__call__(icon) 시그니처
    assert calls == ["open"]


def test_quit_item_triggers_callback():
    calls = []
    menu = build_menu(
        on_open=lambda: None,
        on_toggle_watch=lambda: None,
        watch_enabled=lambda: False,
        on_quit=lambda: calls.append("quit"),
    )
    quit_item = list(menu)[-1]
    quit_item(None)
    assert calls == ["quit"]


def test_toggle_watch_item_triggers_callback():
    calls = []
    menu = build_menu(
        on_open=lambda: None,
        on_toggle_watch=lambda: calls.append("toggled"),
        watch_enabled=lambda: True,
        on_quit=lambda: None,
    )
    toggle_item = list(menu)[1]
    toggle_item(None)
    assert calls == ["toggled"]


def test_watch_checked_state_reflects_watch_enabled_true():
    menu = build_menu(
        on_open=lambda: None, on_toggle_watch=lambda: None,
        watch_enabled=lambda: True, on_quit=lambda: None,
    )
    toggle_item = list(menu)[1]
    assert toggle_item.checked is True


def test_watch_checked_state_reflects_watch_enabled_false():
    menu = build_menu(
        on_open=lambda: None, on_toggle_watch=lambda: None,
        watch_enabled=lambda: False, on_quit=lambda: None,
    )
    toggle_item = list(menu)[1]
    assert toggle_item.checked is False


def test_open_item_is_default():
    menu = build_menu(
        on_open=lambda: None, on_toggle_watch=lambda: None,
        watch_enabled=lambda: False, on_quit=lambda: None,
    )
    open_item = list(menu)[0]
    assert open_item.default is True


def test_build_icon_has_title_and_menu():
    icon = build_icon(
        on_open=lambda: None, on_toggle_watch=lambda: None,
        watch_enabled=lambda: False, on_quit=lambda: None,
    )
    assert icon.title == "루미아 브리핑룸"
    assert len(list(icon.menu)) == 4  # 열기, 감시중, 구분선, 종료


def test_menu_has_open_logs_item_before_separator_when_provided():
    calls = []
    menu = build_menu(
        on_open=lambda: None, on_toggle_watch=lambda: None, watch_enabled=lambda: False,
        on_quit=lambda: None, on_open_logs=lambda: calls.append("logs"),
    )
    items = list(menu)
    logs_item = items[2]
    assert logs_item.text == "로그 폴더 열기"
    assert items[-1].text == "종료"
    logs_item(None)
    assert calls == ["logs"]
