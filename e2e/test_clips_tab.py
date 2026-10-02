"""클립 탭 — 카테고리 목록, 재생 화면, 탭을 떠나면 재생 멈춤. 클립은 앱 API 로 저장해 시드한다(실제 ffmpeg 컷)."""

import re

from playwright.sync_api import expect

from e2e.world import KEY_BR


def save_clip(server, cand_suffix="01", category=None):
    body = {"category": category} if category else {}
    return server.api("POST", f"/api/games/{KEY_BR}/candidates/{KEY_BR}_{cand_suffix}/save", body)


def test_C01_default_categories_open_without_an_error_banner(go, page, shot):
    go("/#/clips")
    expect(page.get_by_text("보관함", exact=True).first).to_be_visible()
    expect(page.get_by_text("자동 보관").first).to_be_visible()
    expect(page.get_by_text("찾을 수 없는 폴더")).to_have_count(0)
    expect(page.get_by_text("보관한 클립이 없습니다", exact=False)).to_be_visible()
    shot("empty_category")
    page.get_by_text("자동 보관").first.click()
    expect(page.get_by_text("찾을 수 없는 폴더")).to_have_count(0)


def test_C02_saved_clip_card_opens_the_player_and_back_returns(go, page, server, shot):
    save_clip(server)
    go("/#/clips")
    page.get_by_text("보관함", exact=True).first.click()
    card = page.get_by_text("첫 교전").locator("visible=true").first
    expect(card).to_be_visible()
    shot("card")
    page.get_by_test_id("clip-open").locator("visible=true").first.click()
    expect(page).to_have_url(re.compile(r"#/clips/.+/clip/"))
    page.wait_for_function("() => document.querySelector('video') && document.querySelector('video').currentTime > 0.2", timeout=15000)
    shot("player")
    page.go_back()
    expect(page).not_to_have_url(re.compile(r"/clip/"))
    expect(page.get_by_text("첫 교전").first).to_be_visible()


def test_C03_leaving_the_clips_tab_stops_the_playback(go, page, server):
    save_clip(server)
    go("/#/clips")
    page.get_by_text("보관함", exact=True).first.click()
    page.get_by_test_id("clip-open").locator("visible=true").first.click()
    page.wait_for_function("() => document.querySelector('video') && !document.querySelector('video').paused", timeout=15000)
    page.get_by_role("tab", name="스팀 녹화").click()
    page.wait_for_timeout(500)
    playing = page.evaluate("() => [...document.querySelectorAll('video')].some(v => !v.paused)")
    assert playing is False, "탭을 떠났는데 영상이 계속 재생 중이다"


def test_C04_search_finds_clips_in_every_category(go, page, server, shot):
    save_clip(server, "01")
    save_clip(server, "03", category="하이라이트")
    go("/#/clips")
    search = page.locator('input[aria-label="클립 검색"]:visible')
    search.fill("마지막")
    expect(page.get_by_text("마지막 교전").first).to_be_visible()
    expect(page.get_by_text("첫 교전")).to_have_count(0)
    shot("search")
    search.fill("")
    expect(page.get_by_text("보관함", exact=True).first).to_be_visible()
