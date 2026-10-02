"""영상 파일 탭 — 날짜 > 영상 묶음 > 게임 행, 검색, 열기, 전체 삭제·목록에서 삭제, 원본 없는 영상의 다시 분석."""

import re

from playwright.sync_api import expect

from e2e.world import KEY_BR


def vod_world(world, launch):
    world.seed_default_games()
    a = world.add_vod("방송A", games=2, tail=10)
    b = world.add_vod("방송B", games=1, tail=20, original=False, date_epoch=1789000000.0)
    return launch(), a, b


def bundle(page, name):
    return page.locator("section, div").filter(has_text=f"{name}.mp4").filter(has=page.get_by_text("전체 삭제")).last


def test_D01_vod_tab_groups_by_date_then_video_then_game(world, launch, page, shot):
    server, a, b = vod_world(world, launch)
    page.goto(server.url + "/#/vod")
    expect(page.get_by_text("9월 21일 (월)")).to_be_visible()
    expect(page.get_by_text("날짜 모름")).to_be_visible()
    expect(page.get_by_text("방송A.mp4")).to_be_visible()
    expect(page.locator(f'[data-game="vod_{a}_g01"]')).to_contain_text("게임 1")
    expect(page.locator(f'[data-game="vod_{a}_g02"]')).to_contain_text("#1")
    expect(page.get_by_text("게임 3개", exact=True)).to_be_visible()
    expect(page.get_by_text("분석 완료").first).to_be_visible()
    expect(page.get_by_text("영상 파일을 찾을 수 없습니다")).to_be_visible()
    shot("vod_list")


def test_D02_opening_a_vod_game_plays_it_and_back_returns_to_the_video_list(world, launch, page):
    server, a, b = vod_world(world, launch)
    page.goto(server.url + "/#/vod")
    page.locator(f'[data-game="vod_{a}_g01"]').click()
    expect(page).to_have_url(re.compile(rf"#/vod/game/vod_{a}_g01"))
    expect(page.get_by_text("← 영상 목록")).to_be_visible()
    page.wait_for_function("() => document.querySelector('video') && document.querySelector('video').currentTime > 0.3", timeout=15000)
    page.get_by_text("← 영상 목록").click()
    expect(page.get_by_text("방송A.mp4")).to_be_visible()


def test_D03_search_matches_the_video_name(world, launch, page, shot):
    server, a, b = vod_world(world, launch)
    page.goto(server.url + "/#/vod")
    search = page.locator('input[aria-label="게임 검색"]:visible')
    search.fill("방송b")
    expect(page.get_by_text("방송B.mp4")).to_be_visible()
    expect(page.get_by_text("방송A.mp4")).to_have_count(0)
    shot("vod_search")
    search.fill("")
    expect(page.get_by_text("방송A.mp4")).to_be_visible()


def test_D04_delete_all_of_a_video_removes_its_games_only(world, launch, page, shot):
    server, a, b = vod_world(world, launch)
    page.goto(server.url + "/#/vod")
    head = page.get_by_text("방송A.mp4").locator("xpath=ancestor::div[.//button[normalize-space()='전체 삭제']][1]")
    head.get_by_role("button", name="전체 삭제").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("풀영상")
    shot("vod_delete_all")
    dialog.get_by_role("button", name=re.compile("삭제")).last.click()
    expect(page.locator(f'[data-game="vod_{a}_g01"]')).to_have_count(0)
    expect(page.locator(f'[data-game="vod_{b}_g01"]')).to_have_count(1)
    assert not (world.vod_games / f"vod_{a}_g01").exists()
    assert (world.vod_games / f"vod_{b}_g01").exists()
    assert (world.steam_games / KEY_BR).exists(), "스팀 게임은 그대로여야 한다"


def test_D05_reanalyze_without_the_original_video_explains_it_will_only_recut_clips(world, launch, page, shot):
    server, a, b = vod_world(world, launch)
    page.goto(server.url + "/#/vod")
    head = page.get_by_text("방송B.mp4").locator("xpath=ancestor::div[.//button[normalize-space()='다시 분석']][1]")
    button = head.get_by_role("button", name="다시 분석")
    expect(button).to_be_enabled()
    button.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("원본 영상이 없어")
    expect(dialog).to_contain_text("풀영상에서 클립만 다시 추출")
    shot("vod_reanalyze_no_source")


def test_D06_remove_from_list_when_the_original_is_gone(world, launch, page):
    server, a, b = vod_world(world, launch)
    page.goto(server.url + "/#/vod")
    head = page.get_by_text("방송B.mp4").locator("xpath=ancestor::div[.//button[normalize-space()='목록에서 삭제']][1]")
    head.get_by_role("button", name="목록에서 삭제").click()
    page.get_by_role("dialog").get_by_role("button", name=re.compile("삭제")).last.click()
    expect(page.get_by_text("방송B.mp4")).to_have_count(0)
    expect(page.get_by_text("방송A.mp4")).to_be_visible()
