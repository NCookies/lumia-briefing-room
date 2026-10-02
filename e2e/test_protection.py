"""보관한 클립 보호 — 자동 보관 클립만 지우고, 보관한 클립은 어떤 삭제에도 남는다(확인 창 문구와 결과 모두)."""

import re

from playwright.sync_api import expect

from e2e.world import KEY_BR, KEY_BR2


def save(server, key, suffix, category=None):
    body = {"category": category} if category else {}
    server.api("POST", f"/api/games/{key}/candidates/{key}_{suffix}/save", body)


def mixed(world, launch):
    """KEY_BR: 보관함 1개(첫 교전) + 자동 보관 1개(02). KEY_BR2: 클립 없음."""
    world.seed_default_games()
    server = launch()
    save(server, KEY_BR, "01")
    save(server, KEY_BR, "02", "자동 보관")
    return server


def menu(page, key, item):
    page.locator(f'[data-game="{key}"]').locator("button", has_text="⋯").click()
    page.get_by_role("menuitem", name=item).click()


def clip_files(world, folder):
    return list((world.root / "clips" / folder).glob("*.mp4"))


def test_P01_deleting_auto_clips_keeps_the_archived_one(world, launch, page, shot):
    server = mixed(world, launch)
    page.goto(server.url)
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_contain_text("보관 1")
    menu(page, KEY_BR, "자동 보관 클립 삭제")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text(re.compile(r"자동 보관 클립 1개.*삭제합니다.*보관한 클립 1개는 남습니다", re.S))
    shot("auto_delete_confirm")
    dialog.get_by_role("button", name=re.compile("삭제")).last.click()
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_contain_text("보관 1")
    page.wait_for_timeout(500)
    assert len(clip_files(world, "자동 보관")) == 0
    assert len(clip_files(world, "보관함")) == 1
    page.get_by_role("tab", name="클립").click()
    expect(page.get_by_text("첫 교전").locator("visible=true").first).to_be_visible()


def test_P02_the_auto_clip_menu_is_disabled_without_auto_clips(world, launch, page):
    server = mixed(world, launch)
    page.goto(server.url)
    page.locator(f'[data-game="{KEY_BR2}"]').locator("button", has_text="⋯").click()
    expect(page.get_by_role("menuitem", name="자동 보관 클립 삭제")).to_be_disabled()


def test_P03_deleting_the_whole_game_keeps_archived_clips_in_the_clip_tab(world, launch, page, shot):
    server = mixed(world, launch)
    page.goto(server.url)
    menu(page, KEY_BR, "게임 전체 삭제")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("보관한 클립 1개는 클립 탭에 남습니다")
    shot("game_delete_confirm")
    dialog.get_by_role("button", name=re.compile("삭제")).last.click()
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_have_count(0)
    assert len(clip_files(world, "보관함")) == 1
    assert len(clip_files(world, "자동 보관")) == 0
    server.restart()
    page.goto(server.url)
    expect(page.locator(f'[data-game="{KEY_BR}"]')).to_have_count(0)
    page.get_by_role("tab", name="클립").click()
    page.get_by_test_id("clip-open").locator("visible=true").first.click()
    page.wait_for_function("() => document.querySelector('video') && document.querySelector('video').currentTime > 0.2", timeout=15000)


def test_P04_vod_delete_all_confirm_names_the_archived_clips_that_stay(world, launch, page, shot):
    world.seed_default_games()
    vid = world.add_vod("방송A", games=1, tail=10)
    server = launch()
    key = f"vod_{vid}_g01"
    server.api("POST", f"/api/games/{key}/candidates/{key}_0011/save", {})
    page.goto(server.url + "/#/vod")
    head = page.get_by_text("방송A.mp4").locator("xpath=ancestor::div[.//button[normalize-space()='전체 삭제']][1]")
    head.get_by_role("button", name="전체 삭제").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text(re.compile("보관한 클립 1개"))
    shot("vod_delete_all_with_archived")
    dialog.get_by_role("button", name=re.compile("삭제")).last.click()
    expect(page.locator(f'[data-game="{key}"]')).to_have_count(0)
    assert len(clip_files(world, "보관함")) == 1
