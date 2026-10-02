"""풀영상 화면 — 열기·재생·주소·뒤로 가기·단축키·보관·메모·삭제."""

import re

from playwright.sync_api import expect

from e2e.world import KEY_BR, KEY_OLD


def open_game(page, go, key=KEY_BR):
    go("/")
    page.locator(f'[data-game="{key}"]').click()
    expect(page.get_by_text("← 게임 목록")).to_be_visible()


def video_state(page) -> dict:
    return page.evaluate(
        "() => { const v = document.querySelector('video'); return v ? {t: v.currentTime, paused: v.paused, vol: v.volume, d: v.duration} : null }")


def test_V01_opening_a_game_plays_it_and_lists_the_candidates(go, page, shot):
    open_game(page, go)
    expect(page).to_have_url(re.compile(rf"#/steam/game/{KEY_BR}"))
    page.wait_for_function("() => document.querySelector('video') && document.querySelector('video').currentTime > 0.3", timeout=15000)
    assert video_state(page)["paused"] is False
    candidates = page.get_by_test_id("viewer-candidates")
    expect(candidates).to_contain_text("후보 3개")
    expect(candidates).to_contain_text("첫 교전")
    expect(candidates).to_contain_text("0:03~0:09 (6초)")
    shot("viewer")


def test_V02_back_button_returns_to_the_list_with_folds_kept(go, page):
    go("/")
    page.get_by_text("9월 28일 (월)").click()
    page.locator(f'[data-game="{KEY_BR}"]').click()
    expect(page.get_by_text("← 게임 목록")).to_be_visible()
    page.go_back()
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_be_visible()
    expect(page.locator(f'[data-game="{KEY_OLD}"]')).to_have_count(0)
    page.locator(f'[data-game="{KEY_BR}"]').click()
    page.get_by_text("← 게임 목록").click()
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_be_visible()


def test_V03_the_game_address_opens_the_same_screen_in_a_new_page(go, page, server):
    go(f"/#/steam/game/{KEY_BR}")
    expect(page.get_by_text("← 게임 목록")).to_be_visible()
    go("/#/steam/game/20990101_000000")
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_be_visible()


def test_V04_keyboard_play_seek_volume_and_add_range(go, page, shot):
    open_game(page, go)
    page.wait_for_function("() => document.querySelector('video') && document.querySelector('video').currentTime > 0.3", timeout=15000)
    page.keyboard.press("Space")
    assert video_state(page)["paused"] is True
    page.keyboard.press("Space")
    assert video_state(page)["paused"] is False
    page.keyboard.press("Space")
    before = video_state(page)["t"]
    page.keyboard.press("ArrowRight")
    assert abs(video_state(page)["t"] - (before + 5)) < 0.6
    page.keyboard.press("ArrowLeft")
    assert abs(video_state(page)["t"] - before) < 0.6
    vol = video_state(page)["vol"]
    page.keyboard.press("ArrowDown")
    assert abs(video_state(page)["vol"] - (vol - 0.05)) < 0.02
    page.keyboard.press("ArrowUp")
    assert abs(video_state(page)["vol"] - vol) < 0.02
    candidates = page.get_by_test_id("viewer-candidates")
    page.keyboard.press("n")
    expect(candidates).to_contain_text("후보 4개")
    shot("range_added")


def test_V05_ctrl_arrows_jump_between_candidates(go, page):
    open_game(page, go)
    page.wait_for_function("() => document.querySelector('video') && document.querySelector('video').duration > 0", timeout=15000)
    page.keyboard.press("Control+ArrowRight")
    page.wait_for_timeout(300)
    t1 = video_state(page)["t"]
    page.keyboard.press("Control+ArrowRight")
    page.wait_for_timeout(300)
    t2 = video_state(page)["t"]
    assert t2 > t1 >= 2.5


def test_V06_archive_a_candidate_into_a_category(go, page, world, server, shot):
    open_game(page, go)
    first = page.locator('[data-cand]').first
    first.get_by_role("button", name="보관").click()
    popup = page.get_by_role("dialog")
    expect(popup).to_be_visible()
    expect(popup).to_contain_text("보관함")
    expect(popup).to_contain_text("자동 보관")
    expect(popup).to_contain_text("새 카테고리")
    shot("archive_popup")
    popup.get_by_text("보관함").first.click()
    expect(first.get_by_text("보관됨")).to_be_visible(timeout=20000)
    clips = list((world.root / "clips" / "보관함").glob("*.mp4"))
    assert len(clips) == 1, "보관함 폴더에 클립 영상이 생겨야 한다"
    expect(page.get_by_text("후보 3개")).to_be_visible()
    page.get_by_role("tab", name="클립").click()
    expect(page.get_by_text("1개").first).to_be_visible()


def test_V07_memo_is_saved_and_survives_reopen(go, page, server):
    open_game(page, go)
    first = page.locator('[data-cand]').first
    first.get_by_role("button", name="보관").click()
    page.get_by_role("dialog").get_by_text("보관함").first.click()
    expect(first.get_by_text("보관됨")).to_be_visible(timeout=20000)
    first.get_by_role("button", name=re.compile("메모")).click()
    box = first.get_by_role("textbox")
    box.fill("좋았던 점: 위치 선정")
    first.get_by_role("button", name="저장").click()
    page.get_by_text("← 게임 목록").click()
    page.locator(f'[data-game="{KEY_BR}"]').click()
    first = page.locator('[data-cand]').first
    expect(first.get_by_role("button", name=re.compile("메모 ●"))).to_be_visible()


def test_V08_delete_key_asks_before_removing_a_saved_clip(go, page, world, server):
    open_game(page, go)
    first = page.locator('[data-cand]').first
    first.get_by_role("button", name="보관").click()
    page.get_by_role("dialog").get_by_text("보관함").first.click()
    expect(first.get_by_text("보관됨")).to_be_visible(timeout=20000)
    first.get_by_text("첫 교전").click()
    page.keyboard.press("Delete")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    assert len(list((world.root / "clips" / "보관함").glob("*.mp4"))) == 1
    first.get_by_text("첫 교전").click()
    page.keyboard.press("Delete")
    page.get_by_role("dialog").get_by_role("button", name="삭제").click()
    expect(page.get_by_test_id("viewer-candidates")).to_contain_text("후보 2개", timeout=15000)
    assert len(list((world.root / "clips" / "보관함").glob("*.mp4"))) == 0
