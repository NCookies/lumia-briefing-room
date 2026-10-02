"""스팀 녹화 탭 게임 목록 — release-checklist 의 날짜 머리줄·접기·검색·`⋯` 메뉴·삭제 항목을 대신한다."""

import re

from playwright.sync_api import expect

from e2e.world import KEY_BR, KEY_BR2, KEY_COBALT, KEY_OLD


def game_search(page):
    return page.locator('input[aria-label="게임 검색"]:visible')


def row(page, key):
    return page.locator(f'[data-game="{key}"]')


def test_L01_date_headers_split_the_games_and_the_toolbar_order_is_fixed(go, page, shot):
    go("/")
    expect(page.get_by_text("9월 30일 (수)")).to_be_visible()
    expect(page.get_by_text("9월 28일 (월)")).to_be_visible()
    expect(page.get_by_text("게임 2개 · 클립 0개", exact=False).first).to_be_visible()
    expect(page.get_by_text("게임 4개", exact=True)).to_be_visible()
    for key in (KEY_BR, KEY_BR2, KEY_OLD, KEY_COBALT):
        expect(row(page, key)).to_have_count(1)
    toolbar = page.locator("body").inner_text()
    order = ["날짜 모두 펼치기", "날짜 모두 접기", "삭제 예정만 보기", "과거 녹화 분석", "게임 4개", "이 탭"]
    positions = [toolbar.index(t) for t in order]
    assert positions == sorted(positions), f"도구 줄 순서가 다르다: {order}"
    expect(game_search(page)).to_be_visible()
    shot("list")


def test_L02_rows_show_placement_mode_and_kda(go, page):
    go("/")
    first = row(page, KEY_BR)
    expect(first).to_contain_text("#1")
    expect(first).to_contain_text("랭크")
    expect(first).to_contain_text("5 / 3 / 2")
    expect(first).to_contain_text("후보 3 · 보관 0")
    expect(row(page, KEY_COBALT)).to_contain_text("코발트")
    expect(row(page, KEY_COBALT)).to_contain_text("승리")


def test_L03_a_game_without_full_video_says_so(go, page, shot):
    go("/")
    expect(row(page, KEY_OLD)).to_contain_text("풀영상 없음")
    expect(row(page, KEY_BR)).not_to_contain_text("풀영상 없음")
    shot("no_full_video")


def test_L04_fold_a_day_and_it_stays_folded_after_reload(go, page, shot):
    go("/")
    page.get_by_text("9월 30일 (수)").click()
    expect(row(page, KEY_BR)).to_have_count(0)
    expect(row(page, KEY_OLD)).to_have_count(1)
    shot("folded")
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(row(page, KEY_BR)).to_have_count(0)
    page.get_by_text("날짜 모두 펼치기").click()
    expect(row(page, KEY_BR)).to_have_count(1)
    page.get_by_text("날짜 모두 접기").click()
    expect(row(page, KEY_OLD)).to_have_count(0)


def test_L05_search_keeps_only_matching_games_and_says_where_it_matched(go, page, shot):
    go("/")
    search = game_search(page)
    search.fill("첫 교전")
    expect(row(page, KEY_BR)).to_have_count(1)
    expect(row(page, KEY_BR2)).to_have_count(0)
    expect(row(page, KEY_BR)).to_contain_text("후보")
    shot("search")
    search.fill("")
    expect(row(page, KEY_BR2)).to_have_count(1)


def test_L06_game_menu_items_and_disabled_state(go, page, shot):
    go("/")
    row(page, KEY_OLD).locator("button", has_text="⋯").click()
    menu = page.get_by_role("menu")
    for item in ("게임 정보 수정하기", "다시 분석", "풀영상만 삭제", "자동 보관 클립 삭제", "게임 전체 삭제"):
        expect(menu.get_by_role("menuitem", name=item)).to_be_visible()
    expect(menu.get_by_role("menuitem", name="풀영상만 삭제")).to_be_disabled()
    expect(menu.get_by_role("menuitem", name="게임 전체 삭제")).to_be_enabled()
    shot("menu")


def test_L07_deleting_a_whole_game_removes_the_row_and_it_does_not_come_back(go, page, server, shot):
    go("/")
    row(page, KEY_OLD).locator("button", has_text="⋯").click()
    page.get_by_role("menuitem", name="게임 전체 삭제").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    shot("confirm")
    dialog.get_by_role("button", name=re.compile("삭제")).last.click()
    expect(row(page, KEY_OLD)).to_have_count(0)
    server.restart()
    go("/")
    expect(row(page, KEY_OLD)).to_have_count(0)
    expect(row(page, KEY_BR)).to_have_count(1)


def test_L08_pin_button_explains_itself(go, page):
    go("/")
    pin = row(page, KEY_BR).get_by_role("button", name="고정")
    expect(pin).to_have_attribute("title", re.compile("자동 정리에서 제외"))
