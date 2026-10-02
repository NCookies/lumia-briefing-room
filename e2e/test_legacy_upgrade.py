"""0.1.x 데이터로 새 버전을 처음 켰을 때 — 게임 목록·클립이 그대로 보이고, 원본이 남은 영상은 풀영상을 만들 수 있다.
스팀 녹화 게임은 원본이 이미 없다고 보고, 목록과 클립 조회만 확인한다."""

import re

from playwright.sync_api import expect

STEAM_KEY = "20260928_160025"
PLAYING = "() => document.querySelector('video') && document.querySelector('video').currentTime > 0.2"
SLOW = 60000  # 옛 클립 재생기는 재생용 변환 영상을 먼저 만든다



def snapshot(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def test_U01_old_steam_game_shows_in_the_list_and_its_clips_play(legacy_world, launch, page, shot):
    legacy_world.add_legacy_steam_clips(STEAM_KEY, count=2)
    server = launch()
    page.goto(server.url)
    row = page.locator(f'[data-game="{STEAM_KEY}"]')
    expect(row).to_be_visible()
    expect(row).to_contain_text("풀영상 없음")
    expect(row).to_contain_text("#3")
    shot("legacy_list")
    row.click()
    expect(page.get_by_text("← 게임 목록")).to_be_visible()
    expect(page.get_by_text("이전 버전", exact=False).first).to_be_visible()
    expect(page.get_by_text("보관한 클립 2개")).to_be_visible()
    shot("legacy_game_opened")
    page.get_by_text("옛 교전 2").first.click()
    page.wait_for_function(PLAYING, timeout=SLOW)


def test_U02_old_layout_clip_tab_explains_and_leads_to_the_move_screen(legacy_world, launch, page, shot):
    """옛 경로 모드는 카테고리가 없다(spec/ui.md). 클립 탭은 클립이 사라지지 않았다는 안내와 저장 폴더 설정으로 가는 버튼을 보인다."""
    legacy_world.add_legacy_steam_clips(STEAM_KEY, count=2)
    server = launch()
    page.goto(server.url + "/#/clips")
    notice = page.get_by_test_id("legacy-layout-notice")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("클립은 사라지지 않았습니다")
    expect(notice).to_contain_text("새 구조로 옮기세요")
    expect(page.get_by_text("옛 교전 1")).to_have_count(0)
    shot("legacy_clips_tab")
    notice.get_by_role("button", name="저장 폴더 설정 열기").click()
    expect(page.get_by_role("button", name=re.compile("새 구조로 옮기기"))).to_be_visible()
    shot("legacy_storage_settings")
    page.keyboard.press("Escape")
    page.get_by_role("tab", name="스팀 녹화").click()
    expect(page.locator(f'[data-game="{STEAM_KEY}"]')).to_be_visible()


def test_U03_info_files_move_out_of_the_clip_folder_and_a_second_start_changes_nothing(legacy_world, launch, page):
    world = legacy_world
    world.add_legacy_steam_clips(STEAM_KEY, count=2)
    server = launch()
    page.goto(server.url)
    expect(page.locator(f'[data-game="{STEAM_KEY}"]')).to_be_visible()
    left = snapshot(world.old_clips)
    assert all(name.endswith(".mp4") for name in left), f"클립 폴더에 영상 외 파일이 남았다: {left}"
    assert len(left) == 2
    library = world.home / "Local" / "LumiaBriefingRoom" / "library"
    first = snapshot(library)
    assert any(n.endswith(".json") for n in first) and any(n.endswith(".jpg") for n in first)
    server.restart()
    page.goto(server.url)
    expect(page.locator(f'[data-game="{STEAM_KEY}"]')).to_be_visible()
    assert snapshot(world.old_clips) == left
    assert snapshot(library) == first
    expect(page.get_by_text("클립 정보를 옮기지 못했습니다")).to_have_count(0)


def test_U04_old_video_with_its_original_can_build_full_videos(legacy_world, launch, page, shot):
    vid = legacy_world.add_legacy_vod("방송A", original=True, tail=10)
    server = launch()
    page.goto(server.url + "/#/vod")
    expect(page.get_by_text("방송A.mp4")).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("풀영상 만들기"))).to_be_visible()
    expect(page.locator(f'[data-game="vod_{vid}_g01"]')).to_contain_text("풀영상 없음")
    shot("legacy_vod_with_original")


def test_U05_old_video_without_the_original_still_lists_games_and_plays_clips(legacy_world, launch, page, shot):
    vid = legacy_world.add_legacy_vod("방송B", original=False, tail=20)
    server = launch()
    page.goto(server.url + "/#/vod")
    expect(page.get_by_text("방송B.mp4")).to_be_visible()
    expect(page.get_by_text("영상 파일을 찾을 수 없습니다")).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("풀영상 만들기"))).to_have_count(0)
    row = page.locator(f'[data-game="vod_{vid}_g01"]')
    expect(row).to_contain_text("풀영상 없음")
    shot("legacy_vod_no_original")
    row.click()
    expect(page.get_by_text("방송B 옛 클립 1").first).to_be_visible()
    page.get_by_text("방송B 옛 클립 2").first.click()
    page.wait_for_function(PLAYING, timeout=SLOW)
